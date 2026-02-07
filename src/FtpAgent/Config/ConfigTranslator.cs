using FtpAgent;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using System.Diagnostics;
using System.Text;

namespace FtpAgent.Config;

/// <summary>
/// Translates legacy file ingestion configurations to the new format using
/// GitHub Copilot CLI with Claude Opus 4.5 as the backing LLM.
/// </summary>
public class ConfigTranslator
{
    private readonly ILogger<ConfigTranslator> _logger;
    private readonly CopilotConfig _copilotConfig;
    private readonly string _promptTemplate;

    public ConfigTranslator(
        ILogger<ConfigTranslator> logger,
        IOptions<CopilotConfig> copilotConfig)
    {
        _logger = logger;
        _copilotConfig = copilotConfig.Value;

        // Load the prompt template at startup
        var promptPath = _copilotConfig.ConfigTranslationPromptPath;
        if (File.Exists(promptPath))
        {
            _promptTemplate = File.ReadAllText(promptPath);
            _logger.LogInformation("Loaded config translation prompt from {Path}", promptPath);
        }
        else
        {
            _logger.LogWarning("Prompt template not found at {Path}. Using built-in fallback prompt.", promptPath);
            _promptTemplate = GetFallbackPromptTemplate();
        }
    }

    /// <summary>
    /// Translates a legacy configuration string to the new format using Copilot CLI.
    /// </summary>
    /// <param name="legacyConfig">The raw legacy configuration content.</param>
    /// <returns>The translated configuration in the new format.</returns>
    /// <exception cref="InvalidOperationException">Thrown when translation fails.</exception>
    public async Task<string> TranslateAsync(string legacyConfig)
    {
        if (string.IsNullOrWhiteSpace(legacyConfig))
        {
            throw new ArgumentException("Legacy config cannot be empty", nameof(legacyConfig));
        }

        var prompt = _promptTemplate.Replace("{{LEGACY_CONFIG}}", legacyConfig);

        _logger.LogDebug("Invoking Copilot CLI for config translation ({Length} chars input)", legacyConfig.Length);

        var result = await InvokeCopilotCliAsync(prompt);

        if (string.IsNullOrWhiteSpace(result))
        {
            throw new InvalidOperationException("Copilot CLI returned empty translation result");
        }

        // Extract the config block from the response if wrapped in markdown code fences
        var translatedConfig = ExtractConfigBlock(result);

        _logger.LogDebug("Translation complete ({OutputLength} chars output)", translatedConfig.Length);

        return translatedConfig;
    }

    /// <summary>
    /// Invokes the GitHub Copilot CLI as an external process and captures the output.
    /// </summary>
    private async Task<string> InvokeCopilotCliAsync(string prompt)
    {
        // Build the Copilot CLI command
        // Uses `gh copilot suggest` or a custom agent command depending on configuration
        var arguments = BuildCopilotArguments(prompt);

        var startInfo = new ProcessStartInfo
        {
            FileName = _copilotConfig.CliPath,
            Arguments = arguments,
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

        _logger.LogDebug("Starting process: {FileName} {Arguments}", startInfo.FileName, arguments);

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        // Write prompt to stdin if using pipe mode
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
            _logger.LogError("Copilot CLI timed out after {Timeout} seconds", _copilotConfig.TimeoutSeconds);
            process.Kill(entireProcessTree: true);
            throw new TimeoutException($"Copilot CLI did not respond within {_copilotConfig.TimeoutSeconds} seconds");
        }

        if (process.ExitCode != 0)
        {
            var errorOutput = stderr.ToString().Trim();
            _logger.LogError("Copilot CLI exited with code {ExitCode}. Stderr: {Stderr}", process.ExitCode, errorOutput);
            throw new InvalidOperationException($"Copilot CLI failed (exit code {process.ExitCode}): {errorOutput}");
        }

        return stdout.ToString().Trim();
    }

    /// <summary>
    /// Builds CLI arguments for invoking Copilot. Adjust based on the actual CLI interface.
    /// </summary>
    private string BuildCopilotArguments(string prompt)
    {
        // TODO: Adjust these arguments to match the actual Copilot CLI invocation format.
        // Current implementation assumes `gh copilot` extension with stdin support.
        // Alternative: write prompt to a temp file and pass via --file flag.
        return $"copilot suggest --model {_copilotConfig.Model} --stdin";
    }

    /// <summary>
    /// Extracts a configuration block from a markdown-fenced response.
    /// If the response contains ```json or ```yaml fences, extracts the content within.
    /// </summary>
    private static string ExtractConfigBlock(string response)
    {
        // Look for fenced code blocks (```json ... ``` or ```yaml ... ``` or ``` ... ```)
        var lines = response.Split('\n');
        var inBlock = false;
        var blockContent = new StringBuilder();

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
                blockContent.AppendLine(line);
            }
        }

        // If we extracted a block, return it; otherwise return the full response
        var extracted = blockContent.ToString().Trim();
        return string.IsNullOrEmpty(extracted) ? response.Trim() : extracted;
    }

    private static string GetFallbackPromptTemplate()
    {
        return """
            You are a configuration migration assistant. Translate the following legacy file ingestion
            configuration to the new JSON-based format.

            Legacy configuration:
            {{LEGACY_CONFIG}}

            Translate this to a JSON configuration object with the following structure:
            {
              "name": "<descriptive name>",
              "protocol": "<SFTP|FTP|Exchange>",
              "source": {
                "host": "<hostname>",
                "port": <port>,
                "path": "<remote path>",
                "credentials": "<credential reference>"
              },
              "schedule": {
                "cron": "<cron expression>",
                "timezone": "UTC"
              },
              "processing": {
                "filePattern": "<glob pattern>",
                "archivePath": "<archive path>",
                "errorPath": "<error path>"
              }
            }

            Return ONLY the JSON configuration block, wrapped in ```json code fences.
            """;
    }
}
