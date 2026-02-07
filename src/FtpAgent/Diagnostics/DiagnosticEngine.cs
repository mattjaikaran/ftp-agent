using FtpAgent;
using FtpAgent.State;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace FtpAgent.Diagnostics;

/// <summary>
/// Uses GitHub Copilot CLI with Claude Opus 4.5 to diagnose migration failures.
/// Analyzes error logs and current configuration to suggest fixes.
/// </summary>
public class DiagnosticEngine
{
    private readonly ILogger<DiagnosticEngine> _logger;
    private readonly CopilotConfig _copilotConfig;
    private readonly string _promptTemplate;

    /// <summary>
    /// Known common issues and their resolutions, used to augment LLM diagnosis.
    /// </summary>
    private static readonly Dictionary<string, string> KnownIssues = new(StringComparer.OrdinalIgnoreCase)
    {
        ["ConnectionRefused"] = "Check host/port configuration. Ensure firewall rules allow outbound connections.",
        ["AuthenticationFailed"] = "Verify credential reference points to valid secret. Check username format.",
        ["FileNotFoundException"] = "Verify remote path exists and is accessible with provided credentials.",
        ["PermissionDenied"] = "Check file/directory permissions on remote host. Verify user has read access.",
        ["TimeoutException"] = "Increase connection timeout. Check network connectivity to remote host.",
        ["SchemaValidationError"] = "Config structure does not match expected schema. Review field names and types.",
        ["InvalidCronExpression"] = "Check cron schedule syntax. Ensure 5 or 6 field cron format.",
        ["SftpException"] = "SFTP-specific error. Check host key fingerprint, key exchange algorithms.",
        ["CertificateError"] = "TLS certificate validation failed. Check certificate chain and expiry."
    };

    public DiagnosticEngine(
        ILogger<DiagnosticEngine> logger,
        IOptions<CopilotConfig> copilotConfig)
    {
        _logger = logger;
        _copilotConfig = copilotConfig.Value;

        var promptPath = _copilotConfig.ErrorDiagnosisPromptPath;
        if (File.Exists(promptPath))
        {
            _promptTemplate = File.ReadAllText(promptPath);
            _logger.LogInformation("Loaded error diagnosis prompt from {Path}", promptPath);
        }
        else
        {
            _logger.LogWarning("Diagnosis prompt template not found at {Path}. Using built-in fallback.", promptPath);
            _promptTemplate = GetFallbackPromptTemplate();
        }
    }

    /// <summary>
    /// Diagnoses a file migration failure by analyzing error logs and current configuration.
    /// Uses the Copilot CLI for LLM-powered analysis and augments with known issue patterns.
    /// </summary>
    /// <param name="file">The file entry that failed.</param>
    /// <param name="errors">List of error messages from the failure.</param>
    /// <returns>Diagnostic result with analysis, suggested changes, and optionally a revised config.</returns>
    public async Task<DiagnosticResult> DiagnoseAsync(FileEntry file, List<string> errors)
    {
        _logger.LogInformation("Diagnosing failure for {FileName} ({FileId}). Error count: {ErrorCount}",
            file.Name, file.Id, errors.Count);

        var result = new DiagnosticResult();

        // Step 1: Check against known issues first (fast path)
        var knownDiagnosis = CheckKnownIssues(errors);
        if (knownDiagnosis.Count > 0)
        {
            _logger.LogInformation("Found {Count} known issue matches for {FileName}",
                knownDiagnosis.Count, file.Name);
            result.SuggestedChanges.AddRange(knownDiagnosis);
        }

        // Step 2: Use Copilot CLI for deeper analysis
        try
        {
            var prompt = BuildDiagnosisPrompt(file, errors, knownDiagnosis);
            var llmResponse = await InvokeCopilotCliAsync(prompt);

            var parsed = ParseDiagnosticResponse(llmResponse);
            result.Analysis = parsed.Analysis;
            result.RootCause = parsed.RootCause;
            result.IsRecoverable = parsed.IsRecoverable;

            if (!string.IsNullOrEmpty(parsed.RevisedConfig))
            {
                result.RevisedConfig = parsed.RevisedConfig;
            }

            result.SuggestedChanges.AddRange(parsed.SuggestedChanges);

            _logger.LogInformation("Diagnosis complete for {FileName}. Recoverable: {Recoverable}, RootCause: {RootCause}",
                file.Name, result.IsRecoverable, result.RootCause);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Copilot CLI diagnosis failed for {FileName}. Using known-issue analysis only.", file.Name);
            result.Analysis = $"LLM diagnosis unavailable: {ex.Message}. Known issue analysis: {string.Join("; ", knownDiagnosis)}";
            result.IsRecoverable = false;
        }

        return result;
    }

    /// <summary>
    /// Checks error messages against the known issue database.
    /// </summary>
    private List<string> CheckKnownIssues(List<string> errors)
    {
        var matches = new List<string>();

        foreach (var error in errors)
        {
            foreach (var (pattern, resolution) in KnownIssues)
            {
                if (error.Contains(pattern, StringComparison.OrdinalIgnoreCase))
                {
                    matches.Add($"[{pattern}]: {resolution}");
                }
            }
        }

        return matches.Distinct().ToList();
    }

    /// <summary>
    /// Builds the full diagnosis prompt with file context, errors, and known issue hints.
    /// </summary>
    private string BuildDiagnosisPrompt(FileEntry file, List<string> errors, List<string> knownMatches)
    {
        var errorBlock = string.Join("\n", errors.Select((e, i) => $"  {i + 1}. {e}"));
        var knownBlock = knownMatches.Count > 0
            ? string.Join("\n", knownMatches.Select(k => $"  - {k}"))
            : "  (none)";

        return _promptTemplate
            .Replace("{{FILE_NAME}}", file.Name)
            .Replace("{{FILE_ID}}", file.Id)
            .Replace("{{PROTOCOL}}", file.Protocol)
            .Replace("{{CURRENT_CONFIG}}", file.NewConfig)
            .Replace("{{LEGACY_CONFIG}}", file.LegacyConfig)
            .Replace("{{ERROR_LOGS}}", errorBlock)
            .Replace("{{KNOWN_ISSUES}}", knownBlock)
            .Replace("{{RETRY_COUNT}}", file.RetryCount.ToString());
    }

    /// <summary>
    /// Parses the LLM response into a structured diagnostic result.
    /// Expects a JSON response or structured text with labeled sections.
    /// </summary>
    private DiagnosticResult ParseDiagnosticResponse(string response)
    {
        var result = new DiagnosticResult();

        // Try parsing as JSON first
        try
        {
            using var doc = JsonDocument.Parse(response);
            var root = doc.RootElement;

            if (root.TryGetProperty("analysis", out var analysis))
                result.Analysis = analysis.GetString() ?? string.Empty;

            if (root.TryGetProperty("rootCause", out var rootCause))
                result.RootCause = rootCause.GetString() ?? string.Empty;

            if (root.TryGetProperty("isRecoverable", out var recoverable))
                result.IsRecoverable = recoverable.GetBoolean();

            if (root.TryGetProperty("revisedConfig", out var config))
            {
                result.RevisedConfig = config.ValueKind == JsonValueKind.String
                    ? config.GetString() ?? string.Empty
                    : config.GetRawText();
            }

            if (root.TryGetProperty("suggestedChanges", out var changes) &&
                changes.ValueKind == JsonValueKind.Array)
            {
                foreach (var change in changes.EnumerateArray())
                {
                    var val = change.GetString();
                    if (!string.IsNullOrEmpty(val))
                        result.SuggestedChanges.Add(val);
                }
            }

            return result;
        }
        catch (JsonException)
        {
            // Not JSON, fall through to text parsing
        }

        // Parse as structured text with labeled sections
        result.Analysis = response;
        result.IsRecoverable = response.Contains("recoverable", StringComparison.OrdinalIgnoreCase)
                            || response.Contains("can be fixed", StringComparison.OrdinalIgnoreCase);

        // Extract root cause from "Root cause:" or "Cause:" labels
        var rootCauseLine = response.Split('\n')
            .FirstOrDefault(l => l.TrimStart().StartsWith("Root cause:", StringComparison.OrdinalIgnoreCase)
                              || l.TrimStart().StartsWith("Cause:", StringComparison.OrdinalIgnoreCase));

        if (rootCauseLine is not null)
        {
            result.RootCause = rootCauseLine.Split(':', 2).LastOrDefault()?.Trim() ?? string.Empty;
        }

        // Extract code block as revised config
        var configBlock = ExtractCodeBlock(response);
        if (!string.IsNullOrEmpty(configBlock))
        {
            result.RevisedConfig = configBlock;
        }

        return result;
    }

    /// <summary>
    /// Extracts a code block from markdown-formatted text.
    /// </summary>
    private static string ExtractCodeBlock(string text)
    {
        var lines = text.Split('\n');
        var inBlock = false;
        var block = new StringBuilder();

        foreach (var line in lines)
        {
            if (line.TrimStart().StartsWith("```") && !inBlock)
            {
                inBlock = true;
                continue;
            }
            if (line.TrimStart().StartsWith("```") && inBlock)
            {
                break;
            }
            if (inBlock)
            {
                block.AppendLine(line);
            }
        }

        return block.ToString().Trim();
    }

    /// <summary>
    /// Invokes the Copilot CLI for LLM-powered diagnosis.
    /// </summary>
    private async Task<string> InvokeCopilotCliAsync(string prompt)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = _copilotConfig.CliPath,
            Arguments = $"copilot suggest --model {_copilotConfig.Model} --stdin",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            Environment =
            {
                ["GH_COPILOT_MODEL"] = _copilotConfig.Model
            }
        };

        using var process = new Process { StartInfo = startInfo };
        var stdout = new StringBuilder();
        var stderr = new StringBuilder();

        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is not null)
                stdout.AppendLine(e.Data);
        };

        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null)
                stderr.AppendLine(e.Data);
        };

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        await process.StandardInput.WriteAsync(prompt);
        process.StandardInput.Close();

        var timeout = TimeSpan.FromSeconds(_copilotConfig.TimeoutSeconds);
        using var cts = new CancellationTokenSource(timeout);

        try
        {
            await process.WaitForExitAsync(cts.Token);
        }
        catch (OperationCanceledException)
        {
            process.Kill(entireProcessTree: true);
            throw new TimeoutException($"Copilot CLI diagnosis timed out after {_copilotConfig.TimeoutSeconds} seconds");
        }

        if (process.ExitCode != 0)
        {
            throw new InvalidOperationException(
                $"Copilot CLI diagnosis failed (exit code {process.ExitCode}): {stderr.ToString().Trim()}");
        }

        return stdout.ToString().Trim();
    }

    private static string GetFallbackPromptTemplate()
    {
        return """
            You are a DevOps diagnostic assistant analyzing a file ingestion migration failure.

            ## File Information
            - Name: {{FILE_NAME}}
            - ID: {{FILE_ID}}
            - Protocol: {{PROTOCOL}}
            - Retry Count: {{RETRY_COUNT}}

            ## Current Configuration (new format)
            {{CURRENT_CONFIG}}

            ## Legacy Configuration (original)
            {{LEGACY_CONFIG}}

            ## Error Logs
            {{ERROR_LOGS}}

            ## Known Issue Matches
            {{KNOWN_ISSUES}}

            ## Instructions
            Analyze the error logs and configuration to determine the root cause of the failure.
            Respond with a JSON object containing:
            {
              "analysis": "<detailed analysis of the failure>",
              "rootCause": "<concise root cause>",
              "isRecoverable": true/false,
              "suggestedChanges": ["<change 1>", "<change 2>"],
              "revisedConfig": "<corrected JSON config if recoverable, otherwise empty string>"
            }
            """;
    }
}
