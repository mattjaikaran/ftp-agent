using FtpAgent.CI;
using FtpAgent.Config;
using FtpAgent.Deployment;
using FtpAgent.Diagnostics;
using FtpAgent.Git;
using FtpAgent.Monitoring;
using FtpAgent.State;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using System.Diagnostics;

namespace FtpAgent.Orchestration;

/// <summary>
/// Main autonomous loop that orchestrates the entire migration pipeline.
/// Processes files in batches through: translate -> commit -> build -> deploy -> verify -> diagnose.
/// </summary>
public class BatchOrchestrator
{
    private readonly ILogger<BatchOrchestrator> _logger;
    private readonly AgentConfig _config;
    private readonly ConfigTranslator _configTranslator;
    private readonly NewConfigWriter _configWriter;
    private readonly GitManager _gitManager;
    private readonly GitHubActionsMonitor _ciMonitor;
    private readonly IDeploymentClient _deploymentClient;
    private readonly DatadogClient _datadogClient;
    private readonly DiagnosticEngine _diagnosticEngine;
    private readonly StateStore _stateStore;
    private readonly DryRunFlag _dryRun;
    private readonly List<BatchResult> _batchResults = new();

    public BatchOrchestrator(
        ILogger<BatchOrchestrator> logger,
        IOptions<AgentConfig> config,
        ConfigTranslator configTranslator,
        NewConfigWriter configWriter,
        GitManager gitManager,
        GitHubActionsMonitor ciMonitor,
        IDeploymentClient deploymentClient,
        DatadogClient datadogClient,
        DiagnosticEngine diagnosticEngine,
        StateStore stateStore,
        DryRunFlag dryRun)
    {
        _logger = logger;
        _config = config.Value;
        _configTranslator = configTranslator;
        _configWriter = configWriter;
        _gitManager = gitManager;
        _ciMonitor = ciMonitor;
        _deploymentClient = deploymentClient;
        _datadogClient = datadogClient;
        _diagnosticEngine = diagnosticEngine;
        _stateStore = stateStore;
        _dryRun = dryRun;
    }

    /// <summary>
    /// Runs the autonomous migration loop until all files are processed or cancellation is requested.
    /// </summary>
    public async Task RunAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("Initializing migration state store");
        await _stateStore.InitializeAsync();

        var batchNumber = 0;
        var overallStopwatch = Stopwatch.StartNew();

        while (await _stateStore.HasPendingFiles() && !cancellationToken.IsCancellationRequested)
        {
            batchNumber++;

            if (_config.MaxBatchesPerRun > 0 && batchNumber > _config.MaxBatchesPerRun)
            {
                _logger.LogInformation("Reached maximum batch limit of {MaxBatches}. Stopping.", _config.MaxBatchesPerRun);
                break;
            }

            _logger.LogInformation("=== Starting Batch {BatchNumber} ===", batchNumber);
            var batchResult = await ProcessBatchAsync(batchNumber, cancellationToken);
            _batchResults.Add(batchResult);

            _logger.LogInformation(
                "Batch {BatchNumber} complete: {Succeeded} succeeded, {Failed} failed, {Retrying} retrying. Duration: {Duration}",
                batchNumber, batchResult.Succeeded.Count, batchResult.Failed.Count,
                batchResult.Retrying.Count, batchResult.Duration);

            if (!batchResult.AllSucceeded && _config.StopOnBatchFailure)
            {
                _logger.LogWarning("Batch {BatchNumber} had failures and StopOnBatchFailure is enabled. Halting.", batchNumber);
                break;
            }
        }

        overallStopwatch.Stop();

        // Generate and log the final report
        var report = await _stateStore.GenerateReport();
        report.TotalDuration = overallStopwatch.Elapsed;
        report.BatchResults = _batchResults;

        _logger.LogInformation("Migration run complete.\n{Report}", report.ToSummary());
    }

    private async Task<BatchResult> ProcessBatchAsync(int batchNumber, CancellationToken cancellationToken)
    {
        var batchStopwatch = Stopwatch.StartNew();
        var result = new BatchResult { BatchNumber = batchNumber };

        // Step 1: Get next batch of files
        var files = await _stateStore.GetNextBatch(_config.BatchSize);
        if (files.Count == 0)
        {
            _logger.LogInformation("No more files to process");
            return result;
        }

        _logger.LogInformation("Processing batch of {Count} files", files.Count);

        // Step 2: Translate each file's legacy config
        var translatedFiles = new List<FileEntry>();
        foreach (var file in files)
        {
            cancellationToken.ThrowIfCancellationRequested();

            try
            {
                await _stateStore.MarkInProgress(file.Id);
                _logger.LogInformation("Translating config for {FileName} ({FileId})", file.Name, file.Id);

                var newConfig = await _configTranslator.TranslateAsync(file.LegacyConfig);
                file.NewConfig = newConfig;

                // Write the translated config to the target repo
                await _configWriter.WriteConfigAsync(file);
                translatedFiles.Add(file);

                _logger.LogDebug("Successfully translated {FileName}", file.Name);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to translate config for {FileName}", file.Name);
                await HandleFileFailure(file, $"Translation failed: {ex.Message}", result);
            }
        }

        if (translatedFiles.Count == 0)
        {
            _logger.LogWarning("No files were successfully translated in this batch");
            batchStopwatch.Stop();
            result.Duration = batchStopwatch.Elapsed;
            return result;
        }

        // Step 3: Commit and push changes
        string commitHash;
        try
        {
            var fileNames = string.Join(", ", translatedFiles.Select(f => f.Name));
            var commitMessage = $"migrate: batch {batchNumber} - {translatedFiles.Count} file configs ({fileNames})";
            commitHash = await _gitManager.CommitAndPushAsync(commitMessage);
            result.CommitHash = commitHash;

            _logger.LogInformation("Committed and pushed. Hash: {CommitHash}", commitHash);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to commit and push batch {BatchNumber}", batchNumber);
            foreach (var file in translatedFiles)
            {
                await HandleFileFailure(file, $"Git commit/push failed: {ex.Message}", result);
            }
            batchStopwatch.Stop();
            result.Duration = batchStopwatch.Elapsed;
            return result;
        }

        // Step 4: Wait for CI build
        BuildResult buildResult;
        try
        {
            var ciTimeout = TimeSpan.FromMinutes(_config.CiBuildTimeoutMinutes);
            _logger.LogInformation("Waiting for CI build to complete (timeout: {Timeout})", ciTimeout);
            buildResult = await _ciMonitor.WaitForWorkflowAsync(commitHash, ciTimeout, cancellationToken);

            if (!buildResult.Success)
            {
                _logger.LogError("CI build failed for commit {CommitHash}. Conclusion: {Conclusion}", commitHash, buildResult.Conclusion);
                foreach (var file in translatedFiles)
                {
                    await HandleFileFailure(file, $"CI build failed: {buildResult.Conclusion}. Logs: {buildResult.LogOutput}", result);
                }
                batchStopwatch.Stop();
                result.Duration = batchStopwatch.Elapsed;
                return result;
            }

            _logger.LogInformation("CI build succeeded. Run: {RunId}", buildResult.RunId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error monitoring CI build for commit {CommitHash}", commitHash);
            foreach (var file in translatedFiles)
            {
                await HandleFileFailure(file, $"CI monitoring error: {ex.Message}", result);
            }
            batchStopwatch.Stop();
            result.Duration = batchStopwatch.Elapsed;
            return result;
        }

        // Step 5: Trigger deployment
        if (_dryRun.Enabled)
        {
            _logger.LogInformation("[DRY RUN] Skipping actual deployment");
        }

        DeploymentResult deployResult;
        try
        {
            var deployTimeout = TimeSpan.FromMinutes(_config.DeployWaitTimeoutMinutes);
            _logger.LogInformation("Triggering deployment for commit {CommitHash}", commitHash);

            deployResult = await _deploymentClient.TriggerDeploymentAsync(commitHash, "production");

            if (string.IsNullOrEmpty(deployResult.DeploymentId))
            {
                throw new InvalidOperationException("Deployment trigger returned empty deployment ID");
            }

            result.DeploymentId = deployResult.DeploymentId;
            _logger.LogInformation("Deployment triggered. ID: {DeploymentId}. Waiting for completion...", deployResult.DeploymentId);

            deployResult = await _deploymentClient.WaitForDeploymentAsync(deployResult.DeploymentId, deployTimeout);

            if (!deployResult.Success)
            {
                _logger.LogError("Deployment failed: {Error}", deployResult.ErrorMessage);
                foreach (var file in translatedFiles)
                {
                    await HandleFileFailure(file, $"Deployment failed: {deployResult.ErrorMessage}", result);
                }
                batchStopwatch.Stop();
                result.Duration = batchStopwatch.Elapsed;
                return result;
            }

            _logger.LogInformation("Deployment succeeded: {DeploymentId}", deployResult.DeploymentId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Deployment error for batch {BatchNumber}", batchNumber);
            foreach (var file in translatedFiles)
            {
                await HandleFileFailure(file, $"Deployment error: {ex.Message}", result);
            }
            batchStopwatch.Stop();
            result.Duration = batchStopwatch.Elapsed;
            return result;
        }

        // Step 6: Wait for logs to propagate, then verify via Datadog
        _logger.LogInformation("Waiting {Delay} minutes for logs to propagate before verification",
            _config.DatadogCheckDelayMinutes);
        await Task.Delay(TimeSpan.FromMinutes(_config.DatadogCheckDelayMinutes), cancellationToken);

        var logWindow = TimeSpan.FromMinutes(_config.LogQueryWindowMinutes);

        foreach (var file in translatedFiles)
        {
            cancellationToken.ThrowIfCancellationRequested();

            try
            {
                _logger.LogInformation("Verifying deployment for {FileName} via Datadog", file.Name);
                var logResult = await _datadogClient.QueryLogsAsync(file.Name, logWindow);

                if (logResult.HasErrors)
                {
                    _logger.LogWarning("Errors detected for {FileName}: {ErrorCount} errors", file.Name, logResult.ErrorCount);

                    // Step 7: Run diagnostic engine on failures
                    var diagnostic = await _diagnosticEngine.DiagnoseAsync(file, logResult.ErrorMessages);

                    if (diagnostic.IsRecoverable && !string.IsNullOrEmpty(diagnostic.RevisedConfig))
                    {
                        _logger.LogInformation("Diagnostic engine suggests recoverable fix for {FileName}. Queueing retry.", file.Name);
                        file.NewConfig = diagnostic.RevisedConfig;
                        file.LastError = $"Auto-diagnosed: {diagnostic.RootCause}";
                        await _stateStore.IncrementRetry(file.Id, file.LastError);
                        result.Retrying.Add(file);
                    }
                    else
                    {
                        await HandleFileFailure(file, $"Post-deploy errors: {string.Join("; ", logResult.ErrorMessages.Take(3))}", result);
                    }
                }
                else if (logResult.FileProcessedSuccessfully)
                {
                    _logger.LogInformation("Verification passed for {FileName}", file.Name);
                    file.Status = MigrationStatus.Success;
                    file.CommitHash = commitHash;
                    file.DeploymentId = result.DeploymentId;
                    await _stateStore.MarkSuccess(file.Id);
                    result.Succeeded.Add(file);
                }
                else
                {
                    _logger.LogWarning("No logs found for {FileName}. File may not have been processed yet. Marking for retry.", file.Name);
                    file.LastError = "No processing logs found in Datadog after deployment";
                    await _stateStore.IncrementRetry(file.Id, file.LastError);
                    result.Retrying.Add(file);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error verifying {FileName} via Datadog", file.Name);
                await HandleFileFailure(file, $"Verification error: {ex.Message}", result);
            }
        }

        batchStopwatch.Stop();
        result.Duration = batchStopwatch.Elapsed;
        return result;
    }

    /// <summary>
    /// Handles a file failure by either queueing for retry or marking as permanently failed.
    /// </summary>
    private async Task HandleFileFailure(FileEntry file, string error, BatchResult batchResult)
    {
        file.LastError = error;

        if (file.RetryCount < _config.MaxRetriesPerFile)
        {
            _logger.LogWarning("File {FileName} failed (attempt {Attempt}/{Max}): {Error}. Queueing retry.",
                file.Name, file.RetryCount + 1, _config.MaxRetriesPerFile, error);
            await _stateStore.IncrementRetry(file.Id, error);
            batchResult.Retrying.Add(file);
        }
        else
        {
            _logger.LogError("File {FileName} permanently failed after {Max} attempts: {Error}",
                file.Name, _config.MaxRetriesPerFile, error);
            await _stateStore.MarkFailed(file.Id, error);
            batchResult.Failed.Add(file);
        }
    }
}
