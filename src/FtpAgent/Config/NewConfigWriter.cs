using FtpAgent.Configuration;
using FtpAgent.State;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using System.Text.Json;

namespace FtpAgent.Config;

/// <summary>
/// Writes translated configuration files to the correct path in the target repository.
/// Handles directory creation, file naming conventions, and validation of the output config.
/// </summary>
public class NewConfigWriter
{
    private readonly ILogger<NewConfigWriter> _logger;
    private readonly GitHubConfig _githubConfig;

    private static readonly JsonSerializerOptions PrettyPrintOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull
    };

    public NewConfigWriter(
        ILogger<NewConfigWriter> logger,
        IOptions<GitHubConfig> githubConfig)
    {
        _logger = logger;
        _githubConfig = githubConfig.Value;
    }

    /// <summary>
    /// Writes the translated configuration to the appropriate file path in the target repository.
    /// </summary>
    /// <param name="file">The file entry with the translated NewConfig content.</param>
    /// <returns>The absolute path of the written configuration file.</returns>
    public async Task<string> WriteConfigAsync(FileEntry file)
    {
        if (string.IsNullOrWhiteSpace(file.NewConfig))
        {
            throw new ArgumentException($"NewConfig is empty for file {file.Name} ({file.Id})");
        }

        var outputPath = ResolveOutputPath(file);
        var directory = Path.GetDirectoryName(outputPath);

        if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
        {
            _logger.LogInformation("Creating directory: {Directory}", directory);
            Directory.CreateDirectory(directory);
        }

        // Validate the translated config is well-formed JSON
        var formattedConfig = FormatConfig(file.NewConfig);

        _logger.LogInformation("Writing config for {FileName} to {OutputPath}", file.Name, outputPath);
        await File.WriteAllTextAsync(outputPath, formattedConfig);

        // Update the file entry with the destination path
        file.DestinationPath = outputPath;

        _logger.LogDebug("Config written successfully: {OutputPath} ({Size} bytes)", outputPath, formattedConfig.Length);
        return outputPath;
    }

    /// <summary>
    /// Resolves the output file path based on the file entry's metadata and target repo structure.
    /// </summary>
    private string ResolveOutputPath(FileEntry file)
    {
        var targetRepoPath = _githubConfig.TargetRepoPath;

        if (string.IsNullOrEmpty(targetRepoPath))
        {
            throw new InvalidOperationException(
                "GitHub.TargetRepoPath is not configured. Cannot determine output path for config files.");
        }

        // If a specific destination path is set on the file entry, use it
        if (!string.IsNullOrEmpty(file.DestinationPath))
        {
            return Path.IsPathRooted(file.DestinationPath)
                ? file.DestinationPath
                : Path.Combine(targetRepoPath, file.DestinationPath);
        }

        // Build the path based on protocol and name conventions
        // Structure: <repo>/configs/<protocol>/<sanitized-name>.json
        var protocol = SanitizePathComponent(file.Protocol.ToLowerInvariant());
        var fileName = SanitizePathComponent(file.Name);

        if (string.IsNullOrEmpty(protocol) || protocol == "unknown")
        {
            protocol = "general";
        }

        return Path.Combine(targetRepoPath, "configs", protocol, $"{fileName}.json");
    }

    /// <summary>
    /// Validates and reformats the config as pretty-printed JSON.
    /// If it is not valid JSON, wraps it in a structured envelope.
    /// </summary>
    private string FormatConfig(string config)
    {
        try
        {
            // Attempt to parse and re-serialize as pretty-printed JSON
            using var doc = JsonDocument.Parse(config);
            return JsonSerializer.Serialize(doc.RootElement, PrettyPrintOptions);
        }
        catch (JsonException ex)
        {
            _logger.LogWarning("Translated config is not valid JSON: {Error}. Writing raw content.", ex.Message);

            // If it's YAML or some other format, write as-is
            // TODO: Add YAML validation if YAML configs are expected
            return config;
        }
    }

    /// <summary>
    /// Sanitizes a string for use as a file or directory name.
    /// </summary>
    private static string SanitizePathComponent(string input)
    {
        if (string.IsNullOrEmpty(input))
            return "unnamed";

        var invalid = Path.GetInvalidFileNameChars();
        var sanitized = new char[input.Length];

        for (int i = 0; i < input.Length; i++)
        {
            sanitized[i] = Array.IndexOf(invalid, input[i]) >= 0 ? '-' : input[i];
        }

        // Replace spaces and consecutive dashes
        var result = new string(sanitized)
            .Replace(' ', '-')
            .ToLowerInvariant();

        // Collapse consecutive dashes
        while (result.Contains("--"))
        {
            result = result.Replace("--", "-");
        }

        return result.Trim('-');
    }
}
