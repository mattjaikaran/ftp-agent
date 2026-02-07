using FtpAgent.Configuration;
using FtpAgent.Infrastructure;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using System.Text;

namespace FtpAgent.Config;

/// <summary>
/// Translates legacy file ingestion configurations to the new format using
/// GitHub Copilot CLI with Claude Opus 4.5 as the backing LLM.
/// </summary>
public class ConfigTranslator
{
    private readonly ILogger<ConfigTranslator> _logger;
    private readonly CopilotCliRunner _copilotRunner;
    private readonly string _promptTemplate;

    public ConfigTranslator(
        ILogger<ConfigTranslator> logger,
        IOptions<CopilotConfig> copilotConfig,
        CopilotCliRunner copilotRunner)
    {
        _logger = logger;
        _copilotRunner = copilotRunner;

        var promptPath = copilotConfig.Value.ConfigTranslationPromptPath;
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
    public async Task<string> TranslateAsync(string legacyConfig)
    {
        if (string.IsNullOrWhiteSpace(legacyConfig))
        {
            throw new ArgumentException("Legacy config cannot be empty", nameof(legacyConfig));
        }

        var prompt = _promptTemplate.Replace("{{LEGACY_CONFIG}}", legacyConfig);

        _logger.LogDebug("Invoking Copilot CLI for config translation ({Length} chars input)", legacyConfig.Length);

        var result = await _copilotRunner.InvokeAsync(prompt);

        if (string.IsNullOrWhiteSpace(result))
        {
            throw new InvalidOperationException("Copilot CLI returned empty translation result");
        }

        var translatedConfig = ExtractConfigBlock(result);
        _logger.LogDebug("Translation complete ({OutputLength} chars output)", translatedConfig.Length);

        return translatedConfig;
    }

    /// <summary>
    /// Extracts a configuration block from a markdown-fenced response.
    /// </summary>
    internal static string ExtractConfigBlock(string response)
    {
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
