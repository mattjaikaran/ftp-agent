using System.Diagnostics;
using System.Text;
using FtpAgent.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace FtpAgent.Infrastructure;

/// <summary>
/// Shared service for invoking the GitHub Copilot CLI as an external process.
/// Used by ConfigTranslator and DiagnosticEngine to eliminate duplicate process management code.
/// </summary>
public class CopilotCliRunner
{
    private readonly ILogger<CopilotCliRunner> _logger;
    private readonly CopilotConfig _config;

    public CopilotCliRunner(
        ILogger<CopilotCliRunner> logger,
        IOptions<CopilotConfig> config)
    {
        _logger = logger;
        _config = config.Value;
    }

    /// <summary>
    /// Invokes the Copilot CLI with the given prompt and returns the stdout output.
    /// </summary>
    /// <param name="prompt">The full prompt text to send via stdin.</param>
    /// <returns>The CLI's stdout output, trimmed.</returns>
    /// <exception cref="TimeoutException">Thrown when the CLI doesn't respond within the configured timeout.</exception>
    /// <exception cref="InvalidOperationException">Thrown when the CLI exits with a non-zero code.</exception>
    public async Task<string> InvokeAsync(string prompt)
    {
        var arguments = $"copilot suggest --model {_config.Model} --stdin";

        var startInfo = new ProcessStartInfo
        {
            FileName = _config.CliPath,
            Arguments = arguments,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            Environment =
            {
                ["GH_COPILOT_MODEL"] = _config.Model
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

        _logger.LogDebug("Starting Copilot CLI: {FileName} {Arguments}", startInfo.FileName, arguments);

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        await process.StandardInput.WriteAsync(prompt);
        process.StandardInput.Close();

        var timeout = TimeSpan.FromSeconds(_config.TimeoutSeconds);
        using var cts = new CancellationTokenSource(timeout);

        try
        {
            await process.WaitForExitAsync(cts.Token);
        }
        catch (OperationCanceledException)
        {
            _logger.LogError("Copilot CLI timed out after {Timeout} seconds", _config.TimeoutSeconds);
            process.Kill(entireProcessTree: true);
            throw new TimeoutException($"Copilot CLI did not respond within {_config.TimeoutSeconds} seconds");
        }

        if (process.ExitCode != 0)
        {
            var errorOutput = stderr.ToString().Trim();
            _logger.LogError("Copilot CLI exited with code {ExitCode}: {Stderr}", process.ExitCode, errorOutput);
            throw new InvalidOperationException(
                $"Copilot CLI failed (exit code {process.ExitCode}): {errorOutput}");
        }

        return stdout.ToString().Trim();
    }
}
