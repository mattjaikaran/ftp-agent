using FtpAgent.State;
using Microsoft.Extensions.Logging;
using System.Text.RegularExpressions;

namespace FtpAgent.Config;

/// <summary>
/// Parses legacy file ingestion configurations from CSV or structured text format
/// into a list of FileEntry objects for processing.
/// </summary>
public class LegacyConfigParser
{
    private readonly ILogger<LegacyConfigParser> _logger;

    // Expected CSV column headers (case-insensitive matching)
    private static readonly string[] RequiredColumns = { "id", "name", "config" };

    public LegacyConfigParser(ILogger<LegacyConfigParser> logger)
    {
        _logger = logger;
    }

    /// <summary>
    /// Parses a CSV file containing legacy file ingestion configurations.
    /// Expected format: Id,Name,Protocol,SourcePath,Host,Port,Path,Schedule,FilePattern,...
    /// The raw config is preserved as a single string for translation.
    /// </summary>
    /// <param name="filePath">Path to the legacy configuration CSV file.</param>
    /// <returns>List of FileEntry objects representing each file to be migrated.</returns>
    public async Task<List<FileEntry>> ParseFromFileAsync(string filePath)
    {
        if (!File.Exists(filePath))
        {
            throw new FileNotFoundException($"Legacy config source file not found: {filePath}", filePath);
        }

        _logger.LogInformation("Parsing legacy configuration from {FilePath}", filePath);

        var lines = await File.ReadAllLinesAsync(filePath);

        if (lines.Length < 2)
        {
            throw new InvalidDataException($"Legacy config file must have at least a header row and one data row. Found {lines.Length} lines.");
        }

        var headers = ParseCsvLine(lines[0]).Select(h => h.Trim().ToLowerInvariant()).ToList();
        ValidateHeaders(headers);

        var entries = new List<FileEntry>();
        var errorCount = 0;

        for (int i = 1; i < lines.Length; i++)
        {
            if (string.IsNullOrWhiteSpace(lines[i]))
                continue;

            try
            {
                var values = ParseCsvLine(lines[i]);
                var entry = MapToFileEntry(headers, values, i + 1);
                entries.Add(entry);
            }
            catch (Exception ex)
            {
                errorCount++;
                _logger.LogWarning(ex, "Failed to parse line {LineNumber}: {Line}", i + 1, lines[i]);
            }
        }

        _logger.LogInformation("Parsed {Count} file entries from {FilePath} ({Errors} parse errors)",
            entries.Count, filePath, errorCount);

        return entries;
    }

    /// <summary>
    /// Parses a raw multi-line config block (non-CSV) by splitting on section delimiters.
    /// Handles INI-style, pipe-delimited, or proprietary config formats.
    /// </summary>
    /// <param name="configContent">Raw text content of the configuration.</param>
    /// <returns>List of FileEntry objects.</returns>
    public List<FileEntry> ParseFromText(string configContent)
    {
        var entries = new List<FileEntry>();
        var sections = SplitIntoSections(configContent);

        foreach (var section in sections)
        {
            if (string.IsNullOrWhiteSpace(section))
                continue;

            var entry = new FileEntry
            {
                Id = ExtractField(section, "id") ?? Guid.NewGuid().ToString("N")[..8],
                Name = ExtractField(section, "name") ?? ExtractField(section, "filename") ?? "unknown",
                LegacyConfig = section.Trim(),
                Protocol = ExtractField(section, "protocol") ?? DetectProtocol(section),
                SourcePath = ExtractField(section, "source") ?? ExtractField(section, "path") ?? string.Empty,
                Status = MigrationStatus.Pending
            };

            entries.Add(entry);
        }

        _logger.LogInformation("Parsed {Count} file entries from text content", entries.Count);
        return entries;
    }

    private void ValidateHeaders(List<string> headers)
    {
        var missing = RequiredColumns.Where(rc => !headers.Contains(rc)).ToList();
        if (missing.Count > 0)
        {
            // Try alternative column names before failing
            var alternatives = new Dictionary<string, string[]>
            {
                ["id"] = new[] { "file_id", "fileid", "identifier" },
                ["name"] = new[] { "file_name", "filename", "description" },
                ["config"] = new[] { "configuration", "legacy_config", "settings" }
            };

            var trulyMissing = missing.Where(m =>
            {
                if (!alternatives.ContainsKey(m)) return true;
                return !alternatives[m].Any(alt => headers.Contains(alt));
            }).ToList();

            if (trulyMissing.Count > 0)
            {
                throw new InvalidDataException(
                    $"Legacy config CSV is missing required columns: {string.Join(", ", trulyMissing)}. " +
                    $"Found columns: {string.Join(", ", headers)}");
            }
        }
    }

    private FileEntry MapToFileEntry(List<string> headers, List<string> values, int lineNumber)
    {
        string GetValue(params string[] possibleHeaders)
        {
            foreach (var h in possibleHeaders)
            {
                var index = headers.IndexOf(h);
                if (index >= 0 && index < values.Count)
                    return values[index].Trim();
            }
            return string.Empty;
        }

        var id = GetValue("id", "file_id", "fileid", "identifier");
        var name = GetValue("name", "file_name", "filename", "description");

        if (string.IsNullOrEmpty(id))
        {
            id = $"file-{lineNumber:D4}";
        }

        if (string.IsNullOrEmpty(name))
        {
            name = $"unnamed-{id}";
        }

        // Build the legacy config as the full row data (all columns as key=value pairs)
        var legacyConfigParts = new List<string>();
        for (int i = 0; i < headers.Count && i < values.Count; i++)
        {
            legacyConfigParts.Add($"{headers[i]}={values[i]}");
        }

        return new FileEntry
        {
            Id = id,
            Name = name,
            LegacyConfig = string.Join("\n", legacyConfigParts),
            Protocol = GetValue("protocol", "type", "transfer_type"),
            SourcePath = GetValue("source_path", "source", "remote_path"),
            Status = MigrationStatus.Pending
        };
    }

    /// <summary>
    /// Parses a CSV line handling quoted fields with embedded commas.
    /// </summary>
    private static List<string> ParseCsvLine(string line)
    {
        var fields = new List<string>();
        var current = new System.Text.StringBuilder();
        var inQuotes = false;

        for (int i = 0; i < line.Length; i++)
        {
            var c = line[i];

            if (c == '"')
            {
                if (inQuotes && i + 1 < line.Length && line[i + 1] == '"')
                {
                    current.Append('"');
                    i++; // skip escaped quote
                }
                else
                {
                    inQuotes = !inQuotes;
                }
            }
            else if (c == ',' && !inQuotes)
            {
                fields.Add(current.ToString());
                current.Clear();
            }
            else
            {
                current.Append(c);
            }
        }

        fields.Add(current.ToString());
        return fields;
    }

    /// <summary>
    /// Splits configuration text into individual sections based on common delimiters.
    /// </summary>
    private static List<string> SplitIntoSections(string content)
    {
        // Try splitting on common section delimiters
        // Pattern 1: Sections separated by blank lines
        var sections = Regex.Split(content, @"\n\s*\n").Where(s => !string.IsNullOrWhiteSpace(s)).ToList();

        if (sections.Count > 1)
            return sections;

        // Pattern 2: INI-style [Section] headers
        sections = Regex.Split(content, @"(?=\[[\w\-\.]+\])").Where(s => !string.IsNullOrWhiteSpace(s)).ToList();

        if (sections.Count > 1)
            return sections;

        // Pattern 3: Delimiter lines (----, ====, etc.)
        sections = Regex.Split(content, @"\n[-=]{3,}\n").Where(s => !string.IsNullOrWhiteSpace(s)).ToList();

        return sections;
    }

    private static string? ExtractField(string text, string fieldName)
    {
        var pattern = $@"(?:^|\n)\s*{Regex.Escape(fieldName)}\s*[=:]\s*(.+?)(?:\n|$)";
        var match = Regex.Match(text, pattern, RegexOptions.IgnoreCase);
        return match.Success ? match.Groups[1].Value.Trim() : null;
    }

    private static string DetectProtocol(string config)
    {
        var lower = config.ToLowerInvariant();
        if (lower.Contains("sftp")) return "SFTP";
        if (lower.Contains("exchange") || lower.Contains("ews")) return "Exchange";
        if (lower.Contains("ftp")) return "FTP";
        return "Unknown";
    }
}
