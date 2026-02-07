using FtpAgent.Configuration;
using FtpAgent.State;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;

namespace FtpAgent.Monitoring;

/// <summary>
/// Queries Datadog Logs API to verify post-deployment file processing health.
/// Detects error patterns and confirms successful processing of migrated files.
/// </summary>
public class DatadogClient
{
    private readonly ILogger<DatadogClient> _logger;
    private readonly HttpClient _httpClient;
    private readonly DatadogConfig _config;

    /// <summary>
    /// Known error patterns that indicate file processing failures.
    /// </summary>
    private static readonly string[] ErrorPatterns =
    {
        "FileNotFoundException",
        "ConnectionRefused",
        "AuthenticationFailed",
        "PermissionDenied",
        "TimeoutException",
        "InvalidConfigurationException",
        "SftpException",
        "FtpException",
        "ExchangeServiceException",
        "SchemaValidationError",
        "ParseError",
        "FileFormatException"
    };

    /// <summary>
    /// Patterns that indicate successful file processing.
    /// </summary>
    private static readonly string[] SuccessPatterns =
    {
        "File processed successfully",
        "Ingestion complete",
        "Transfer completed",
        "File moved to archive",
        "Processing finished"
    };

    public DatadogClient(
        ILogger<DatadogClient> logger,
        IHttpClientFactory httpClientFactory,
        IOptions<DatadogConfig> config)
    {
        _logger = logger;
        _httpClient = httpClientFactory.CreateClient("Datadog");
        _config = config.Value;
    }

    /// <summary>
    /// Queries Datadog logs for entries related to the specified file within the given time window.
    /// Analyzes logs for error patterns and success indicators.
    /// </summary>
    /// <param name="fileIdentifier">The file name or identifier to search for in logs.</param>
    /// <param name="window">The time window to search within (from now minus window).</param>
    /// <returns>LogQueryResult with error/success analysis.</returns>
    public async Task<LogQueryResult> QueryLogsAsync(string fileIdentifier, TimeSpan window)
    {
        _logger.LogInformation("Querying Datadog logs for '{FileId}' within {Window} window",
            fileIdentifier, window);

        var result = new LogQueryResult();

        try
        {
            var now = DateTime.UtcNow;
            var from = now - window;

            // Build the Datadog Logs API query
            var query = BuildQuery(fileIdentifier);
            var requestBody = new
            {
                filter = new
                {
                    query,
                    from = from.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                    to = now.ToString("yyyy-MM-ddTHH:mm:ssZ")
                },
                sort = "timestamp",
                page = new { limit = 1000 }
            };

            _logger.LogDebug("Datadog query: {Query} (from: {From}, to: {To})", query, from, now);

            var jsonContent = new StringContent(
                JsonSerializer.Serialize(requestBody),
                Encoding.UTF8,
                "application/json");

            var response = await _httpClient.PostAsync("/api/v2/logs/events/search", jsonContent);
            response.EnsureSuccessStatusCode();

            var responseContent = await response.Content.ReadAsStringAsync();
            var logEntries = ParseLogEntries(responseContent);

            result.TotalLogEntries = logEntries.Count;
            _logger.LogInformation("Found {Count} log entries for '{FileId}'", logEntries.Count, fileIdentifier);

            // Analyze log entries for errors and success patterns
            AnalyzeLogEntries(logEntries, result);

            _logger.LogInformation(
                "Log analysis for '{FileId}': Errors={ErrorCount}, Warnings={WarningCount}, " +
                "ProcessedSuccessfully={Success}",
                fileIdentifier, result.ErrorCount, result.WarningCount, result.FileProcessedSuccessfully);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "Failed to query Datadog logs for '{FileId}'", fileIdentifier);
            throw;
        }

        return result;
    }

    /// <summary>
    /// Builds a Datadog log query string for the given file identifier.
    /// </summary>
    private string BuildQuery(string fileIdentifier)
    {
        var parts = new List<string>();

        // Filter by service name if configured
        if (!string.IsNullOrEmpty(_config.ServiceName))
        {
            parts.Add($"service:{_config.ServiceName}");
        }

        // Filter by environment if configured
        if (!string.IsNullOrEmpty(_config.Environment))
        {
            parts.Add($"env:{_config.Environment}");
        }

        // Search for the file identifier in the message
        parts.Add($"\"{EscapeQueryValue(fileIdentifier)}\"");

        return string.Join(" ", parts);
    }

    /// <summary>
    /// Parses log entries from the Datadog API response.
    /// </summary>
    private List<LogEntry> ParseLogEntries(string responseJson)
    {
        var entries = new List<LogEntry>();

        try
        {
            using var doc = JsonDocument.Parse(responseJson);
            var root = doc.RootElement;

            if (!root.TryGetProperty("data", out var data))
            {
                _logger.LogWarning("Datadog response missing 'data' property");
                return entries;
            }

            foreach (var item in data.EnumerateArray())
            {
                var entry = new LogEntry();

                if (item.TryGetProperty("attributes", out var attrs))
                {
                    if (attrs.TryGetProperty("message", out var message))
                    {
                        entry.Message = message.GetString() ?? string.Empty;
                    }

                    if (attrs.TryGetProperty("status", out var status))
                    {
                        entry.Level = status.GetString() ?? "info";
                    }

                    if (attrs.TryGetProperty("timestamp", out var timestamp))
                    {
                        entry.Timestamp = timestamp.GetString() ?? string.Empty;
                    }

                    if (attrs.TryGetProperty("tags", out var tags) &&
                        tags.ValueKind == JsonValueKind.Array)
                    {
                        entry.Tags = tags.EnumerateArray()
                            .Select(t => t.GetString() ?? string.Empty)
                            .ToList();
                    }
                }

                entries.Add(entry);
            }
        }
        catch (JsonException ex)
        {
            _logger.LogWarning(ex, "Failed to parse Datadog response JSON");
        }

        return entries;
    }

    /// <summary>
    /// Analyzes parsed log entries for error and success patterns.
    /// </summary>
    private void AnalyzeLogEntries(List<LogEntry> entries, LogQueryResult result)
    {
        foreach (var entry in entries)
        {
            // Check for errors
            if (entry.Level is "error" or "critical" or "fatal" or "emergency")
            {
                result.ErrorCount++;
                result.ErrorMessages.Add(TruncateMessage(entry.Message, 500));
                result.HasErrors = true;
            }
            else if (entry.Level == "warn" || entry.Level == "warning")
            {
                result.WarningCount++;
                result.WarningMessages.Add(TruncateMessage(entry.Message, 500));
            }

            // Check for known error patterns in the message regardless of level
            foreach (var pattern in ErrorPatterns)
            {
                if (entry.Message.Contains(pattern, StringComparison.OrdinalIgnoreCase))
                {
                    if (!result.ErrorMessages.Any(e => e.Contains(pattern, StringComparison.OrdinalIgnoreCase)))
                    {
                        result.ErrorCount++;
                        result.ErrorMessages.Add($"[Pattern:{pattern}] {TruncateMessage(entry.Message, 500)}");
                        result.HasErrors = true;
                    }
                    break;
                }
            }

            // Check for success patterns (only if no errors detected for this entry)
            if (!result.HasErrors)
            {
                foreach (var pattern in SuccessPatterns)
                {
                    if (entry.Message.Contains(pattern, StringComparison.OrdinalIgnoreCase))
                    {
                        result.FileProcessedSuccessfully = true;
                        break;
                    }
                }
            }
        }
    }

    private static string EscapeQueryValue(string value)
    {
        return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
    }

    private static string TruncateMessage(string message, int maxLength)
    {
        return message.Length <= maxLength ? message : message[..maxLength] + "...";
    }

    private class LogEntry
    {
        public string Message { get; set; } = string.Empty;
        public string Level { get; set; } = "info";
        public string Timestamp { get; set; } = string.Empty;
        public List<string> Tags { get; set; } = new();
    }
}
