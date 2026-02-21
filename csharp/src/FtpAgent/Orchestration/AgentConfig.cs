namespace FtpAgent.Orchestration;

/// <summary>
/// Core configuration for the autonomous migration agent.
/// Bound from the "Agent" section of appsettings.json.
/// </summary>
public class AgentConfig
{
    /// <summary>
    /// Number of file entries to process per batch before committing and deploying.
    /// Smaller batches reduce blast radius; larger batches improve throughput.
    /// </summary>
    public int BatchSize { get; set; } = 10;

    /// <summary>
    /// Maximum number of retry attempts per individual file before marking as permanently failed.
    /// </summary>
    public int MaxRetriesPerFile { get; set; } = 3;

    /// <summary>
    /// Maximum time to wait for a deployment to complete before treating it as timed out.
    /// </summary>
    public int DeployWaitTimeoutMinutes { get; set; } = 30;

    /// <summary>
    /// Time to wait after deployment completes before checking Datadog logs.
    /// This allows logs to propagate through the pipeline.
    /// </summary>
    public int DatadogCheckDelayMinutes { get; set; } = 5;

    /// <summary>
    /// Time window (in minutes) to query Datadog logs for errors after deployment.
    /// </summary>
    public int LogQueryWindowMinutes { get; set; } = 15;

    /// <summary>
    /// Maximum time to wait for a GitHub Actions workflow run to complete.
    /// </summary>
    public int CiBuildTimeoutMinutes { get; set; } = 20;

    /// <summary>
    /// Path to the legacy configuration source file (CSV or structured format).
    /// </summary>
    public string LegacyConfigSourcePath { get; set; } = string.Empty;

    /// <summary>
    /// Path to the SQLite database file for migration state persistence.
    /// </summary>
    public string StateDatabasePath { get; set; } = "migration-state.db";

    /// <summary>
    /// Whether to halt the entire run when a batch fails, or continue with the next batch.
    /// </summary>
    public bool StopOnBatchFailure { get; set; } = false;

    /// <summary>
    /// Interval in seconds between polling checks for CI/CD status.
    /// </summary>
    public int PollIntervalSeconds { get; set; } = 30;

    /// <summary>
    /// Maximum number of batches to process in a single run (0 = unlimited).
    /// Useful for staged rollouts.
    /// </summary>
    public int MaxBatchesPerRun { get; set; } = 0;
}
