using FtpAgent;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using System.Diagnostics;
using System.Text;

namespace FtpAgent.Git;

/// <summary>
/// Wraps git CLI operations via Process for committing, pushing, and branch management.
/// All operations run against the target repository configured in GitHub settings.
/// </summary>
public class GitManager
{
    private readonly ILogger<GitManager> _logger;
    private readonly GitHubConfig _config;

    public GitManager(
        ILogger<GitManager> logger,
        IOptions<GitHubConfig> config)
    {
        _logger = logger;
        _config = config.Value;
    }

    /// <summary>
    /// Gets the working directory for git operations (the target repository path).
    /// </summary>
    private string WorkingDirectory => _config.TargetRepoPath;

    /// <summary>
    /// Stages all changes, commits with the given message, and pushes to the remote.
    /// </summary>
    /// <param name="message">The commit message.</param>
    /// <returns>The commit hash of the new commit.</returns>
    public async Task<string> CommitAndPushAsync(string message)
    {
        ValidateWorkingDirectory();

        _logger.LogInformation("Staging all changes in {WorkDir}", WorkingDirectory);
        await RunGitAsync("add", "--all");

        // Check if there are staged changes
        var status = await RunGitAsync("status", "--porcelain");
        if (string.IsNullOrWhiteSpace(status))
        {
            _logger.LogWarning("No changes to commit");
            return await GetCurrentCommitHashAsync();
        }

        _logger.LogInformation("Committing: {Message}", message);
        await RunGitAsync("commit", "-m", message);

        var commitHash = await GetCurrentCommitHashAsync();
        _logger.LogInformation("Committed: {CommitHash}", commitHash);

        _logger.LogInformation("Pushing to remote");
        await RunGitAsync("push");

        _logger.LogInformation("Push complete for {CommitHash}", commitHash);
        return commitHash;
    }

    /// <summary>
    /// Checks out the specified branch, creating it if it does not exist.
    /// </summary>
    /// <param name="branch">The branch name to check out.</param>
    public async Task CheckoutBranchAsync(string branch)
    {
        ValidateWorkingDirectory();

        _logger.LogInformation("Checking out branch: {Branch}", branch);

        try
        {
            // Try to check out existing branch
            await RunGitAsync("checkout", branch);
            _logger.LogInformation("Checked out existing branch: {Branch}", branch);
        }
        catch (InvalidOperationException)
        {
            // Branch doesn't exist, create it
            _logger.LogInformation("Branch {Branch} does not exist. Creating from {Base}", branch, _config.BaseBranch);
            await RunGitAsync("checkout", "-b", branch, _config.BaseBranch);
            _logger.LogInformation("Created and checked out new branch: {Branch}", branch);
        }
    }

    /// <summary>
    /// Pulls the latest changes from the remote for the current branch.
    /// </summary>
    public async Task PullAsync()
    {
        ValidateWorkingDirectory();

        _logger.LogInformation("Pulling latest changes");
        await RunGitAsync("pull", "--rebase");
        _logger.LogInformation("Pull complete");
    }

    /// <summary>
    /// Gets the current commit hash (short form).
    /// </summary>
    public async Task<string> GetCurrentCommitHashAsync()
    {
        var hash = await RunGitAsync("rev-parse", "HEAD");
        return hash.Trim();
    }

    /// <summary>
    /// Gets the current branch name.
    /// </summary>
    public async Task<string> GetCurrentBranchAsync()
    {
        var branch = await RunGitAsync("rev-parse", "--abbrev-ref", "HEAD");
        return branch.Trim();
    }

    /// <summary>
    /// Returns the diff summary of staged and unstaged changes.
    /// </summary>
    public async Task<string> GetDiffSummaryAsync()
    {
        var diff = await RunGitAsync("diff", "--stat");
        var staged = await RunGitAsync("diff", "--staged", "--stat");
        return $"Unstaged:\n{diff}\nStaged:\n{staged}";
    }

    /// <summary>
    /// Resets the last commit while keeping changes staged (soft reset).
    /// Used for recovery scenarios.
    /// </summary>
    public async Task SoftResetLastCommitAsync()
    {
        _logger.LogWarning("Soft-resetting last commit");
        await RunGitAsync("reset", "--soft", "HEAD~1");
    }

    /// <summary>
    /// Runs a git command in the target repository working directory.
    /// </summary>
    private async Task<string> RunGitAsync(params string[] arguments)
    {
        var argString = string.Join(" ", arguments.Select(a => a.Contains(' ') ? $"\"{a}\"" : a));

        var startInfo = new ProcessStartInfo
        {
            FileName = "git",
            Arguments = argString,
            WorkingDirectory = WorkingDirectory,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        _logger.LogDebug("git {Arguments} (in {WorkDir})", argString, WorkingDirectory);

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

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(60));
        try
        {
            await process.WaitForExitAsync(cts.Token);
        }
        catch (OperationCanceledException)
        {
            process.Kill(entireProcessTree: true);
            throw new TimeoutException($"git {argString} timed out after 60 seconds");
        }

        var output = stdout.ToString();
        var errorOutput = stderr.ToString();

        if (process.ExitCode != 0)
        {
            _logger.LogError("git {Arguments} failed (exit code {ExitCode}): {Stderr}",
                argString, process.ExitCode, errorOutput);
            throw new InvalidOperationException(
                $"git {argString} failed (exit code {process.ExitCode}): {errorOutput.Trim()}");
        }

        // Git sometimes writes informational messages to stderr (e.g., "Already up to date.")
        if (!string.IsNullOrWhiteSpace(errorOutput))
        {
            _logger.LogDebug("git stderr (info): {Stderr}", errorOutput.Trim());
        }

        return output;
    }

    private void ValidateWorkingDirectory()
    {
        if (string.IsNullOrEmpty(WorkingDirectory))
        {
            throw new InvalidOperationException(
                "GitHub.TargetRepoPath is not configured. Cannot perform git operations.");
        }

        if (!Directory.Exists(Path.Combine(WorkingDirectory, ".git")))
        {
            throw new InvalidOperationException(
                $"Target path is not a git repository: {WorkingDirectory}");
        }
    }
}
