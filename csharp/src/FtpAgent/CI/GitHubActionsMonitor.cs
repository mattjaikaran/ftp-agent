using System.Diagnostics;
using System.Text;
using System.Text.Json;
using FtpAgent.Configuration;
using FtpAgent.Orchestration;
using FtpAgent.State;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace FtpAgent.CI;

/// <summary>
/// Monitors GitHub Actions workflow runs triggered by commits, using the `gh` CLI.
/// Polls for workflow completion and retrieves build status and logs.
/// </summary>
public class GitHubActionsMonitor
{
    private readonly ILogger<GitHubActionsMonitor> _logger;
    private readonly GitHubConfig _githubConfig;
    private readonly AgentConfig _agentConfig;

    public GitHubActionsMonitor(
        ILogger<GitHubActionsMonitor> logger,
        IOptions<GitHubConfig> githubConfig,
        IOptions<AgentConfig> agentConfig)
    {
        _logger = logger;
        _githubConfig = githubConfig.Value;
        _agentConfig = agentConfig.Value;
    }

    /// <summary>
    /// Waits for a GitHub Actions workflow run triggered by the specified commit to complete.
    /// </summary>
    /// <param name="commitHash">The commit SHA that triggered the workflow.</param>
    /// <param name="timeout">Maximum time to wait for completion.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Build result with success/failure status and log output.</returns>
    public async Task<BuildResult> WaitForWorkflowAsync(
        string commitHash,
        TimeSpan timeout,
        CancellationToken cancellationToken = default)
    {
        _logger.LogInformation("Waiting for workflow run for commit {CommitHash} (timeout: {Timeout})",
            commitHash, timeout);

        var deadline = DateTime.UtcNow + timeout;
        var pollInterval = TimeSpan.FromSeconds(_agentConfig.PollIntervalSeconds);
        string? runId = null;

        // Phase 1: Wait for the workflow run to appear
        while (DateTime.UtcNow < deadline && !cancellationToken.IsCancellationRequested)
        {
            runId = await FindWorkflowRunAsync(commitHash);

            if (runId is not null)
            {
                _logger.LogInformation("Found workflow run {RunId} for commit {CommitHash}", runId, commitHash);
                break;
            }

            _logger.LogDebug("Workflow run not yet available for {CommitHash}. Polling in {Interval}s",
                commitHash, pollInterval.TotalSeconds);

            await Task.Delay(pollInterval, cancellationToken);
        }

        if (runId is null)
        {
            return new BuildResult
            {
                Success = false,
                Conclusion = "not_found",
                LogOutput = $"No workflow run found for commit {commitHash} within {timeout}"
            };
        }

        // Phase 2: Poll for workflow completion
        while (DateTime.UtcNow < deadline && !cancellationToken.IsCancellationRequested)
        {
            var (status, conclusion) = await GetWorkflowRunStatusAsync(runId);

            _logger.LogDebug("Workflow run {RunId} status: {Status}, conclusion: {Conclusion}",
                runId, status, conclusion ?? "n/a");

            if (status == "completed")
            {
                var logOutput = await GetWorkflowRunLogsAsync(runId);
                var runUrl = await GetWorkflowRunUrlAsync(runId);

                var success = conclusion == "success";

                if (success)
                {
                    _logger.LogInformation("Workflow run {RunId} completed successfully", runId);
                }
                else
                {
                    _logger.LogWarning("Workflow run {RunId} completed with conclusion: {Conclusion}", runId, conclusion);
                }

                return new BuildResult
                {
                    Success = success,
                    RunId = runId,
                    Conclusion = conclusion ?? "unknown",
                    LogOutput = logOutput,
                    Url = runUrl
                };
            }

            await Task.Delay(pollInterval, cancellationToken);
        }

        return new BuildResult
        {
            Success = false,
            RunId = runId,
            Conclusion = "timed_out",
            LogOutput = $"Workflow run {runId} did not complete within {timeout}"
        };
    }

    /// <summary>
    /// Finds a workflow run associated with the given commit hash.
    /// </summary>
    private async Task<string?> FindWorkflowRunAsync(string commitHash)
    {
        // Use gh CLI to list recent workflow runs and find one matching the commit
        var args = $"run list --repo {_githubConfig.Repository} --commit {commitHash} --json databaseId,status,conclusion --limit 1";

        if (!string.IsNullOrEmpty(_githubConfig.WorkflowName))
        {
            args += $" --workflow \"{_githubConfig.WorkflowName}\"";
        }

        var output = await RunGhAsync(args);

        if (string.IsNullOrWhiteSpace(output) || output.Trim() == "[]")
        {
            return null;
        }

        try
        {
            using var doc = JsonDocument.Parse(output);
            var runs = doc.RootElement;

            if (runs.GetArrayLength() == 0)
                return null;

            var firstRun = runs[0];
            return firstRun.GetProperty("databaseId").ToString();
        }
        catch (JsonException ex)
        {
            _logger.LogWarning(ex, "Failed to parse gh run list output: {Output}", output);
            return null;
        }
    }

    /// <summary>
    /// Gets the status and conclusion of a workflow run.
    /// </summary>
    private async Task<(string status, string? conclusion)> GetWorkflowRunStatusAsync(string runId)
    {
        var output = await RunGhAsync(
            $"run view {runId} --repo {_githubConfig.Repository} --json status,conclusion");

        try
        {
            using var doc = JsonDocument.Parse(output);
            var root = doc.RootElement;

            var status = root.GetProperty("status").GetString() ?? "unknown";
            string? conclusion = null;

            if (root.TryGetProperty("conclusion", out var conclusionProp) &&
                conclusionProp.ValueKind != JsonValueKind.Null)
            {
                conclusion = conclusionProp.GetString();
            }

            return (status, conclusion);
        }
        catch (JsonException ex)
        {
            _logger.LogWarning(ex, "Failed to parse workflow run status: {Output}", output);
            return ("unknown", null);
        }
    }

    /// <summary>
    /// Retrieves the log output of a completed workflow run.
    /// </summary>
    private async Task<string> GetWorkflowRunLogsAsync(string runId)
    {
        try
        {
            // gh run view with --log gives the full log output
            var output = await RunGhAsync(
                $"run view {runId} --repo {_githubConfig.Repository} --log --exit-status",
                timeoutSeconds: 30);

            // Truncate very long logs to avoid memory issues
            const int maxLogLength = 50_000;
            if (output.Length > maxLogLength)
            {
                var truncated = output[..maxLogLength];
                return truncated + $"\n\n[... truncated, {output.Length - maxLogLength} chars omitted ...]";
            }

            return output;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to retrieve logs for run {RunId}. Returning empty logs.", runId);
            return $"[Failed to retrieve logs: {ex.Message}]";
        }
    }

    /// <summary>
    /// Gets the URL for a workflow run.
    /// </summary>
    private async Task<string> GetWorkflowRunUrlAsync(string runId)
    {
        try
        {
            var output = await RunGhAsync(
                $"run view {runId} --repo {_githubConfig.Repository} --json url");

            using var doc = JsonDocument.Parse(output);
            return doc.RootElement.GetProperty("url").GetString() ?? string.Empty;
        }
        catch
        {
            return $"https://github.com/{_githubConfig.Repository}/actions/runs/{runId}";
        }
    }

    /// <summary>
    /// Runs a `gh` CLI command and returns the stdout output.
    /// </summary>
    private async Task<string> RunGhAsync(string arguments, int timeoutSeconds = 60)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = "gh",
            Arguments = arguments,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        _logger.LogDebug("gh {Arguments}", arguments);

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

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds));
        try
        {
            await process.WaitForExitAsync(cts.Token);
        }
        catch (OperationCanceledException)
        {
            process.Kill(entireProcessTree: true);
            throw new TimeoutException($"gh {arguments} timed out after {timeoutSeconds} seconds");
        }

        if (process.ExitCode != 0)
        {
            var errorOutput = stderr.ToString().Trim();
            _logger.LogWarning("gh command returned exit code {ExitCode}: {Stderr}", process.ExitCode, errorOutput);
            throw new InvalidOperationException($"gh {arguments} failed (exit code {process.ExitCode}): {errorOutput}");
        }

        return stdout.ToString();
    }
}
