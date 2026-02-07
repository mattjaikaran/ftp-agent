namespace FtpAgent.State;

/// <summary>
/// Represents a single file ingestion configuration entry being migrated.
/// </summary>
public class FileEntry
{
    public string Id { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public string LegacyConfig { get; set; } = string.Empty;
    public string NewConfig { get; set; } = string.Empty;
    public MigrationStatus Status { get; set; } = MigrationStatus.Pending;
    public int RetryCount { get; set; }
    public string LastError { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
    public string CommitHash { get; set; } = string.Empty;
    public string DeploymentId { get; set; } = string.Empty;

    /// <summary>
    /// Source path of the legacy configuration file.
    /// </summary>
    public string SourcePath { get; set; } = string.Empty;

    /// <summary>
    /// Destination path for the translated configuration in the target repo.
    /// </summary>
    public string DestinationPath { get; set; } = string.Empty;

    /// <summary>
    /// Protocol type: SFTP, FTP, Exchange, etc.
    /// </summary>
    public string Protocol { get; set; } = string.Empty;

    public override string ToString() => $"[{Id}] {Name} ({Status})";
}

/// <summary>
/// Tracks the lifecycle of each file entry through the migration pipeline.
/// </summary>
public enum MigrationStatus
{
    /// <summary>File has not yet been processed.</summary>
    Pending = 0,

    /// <summary>File is currently being translated and deployed.</summary>
    InProgress = 1,

    /// <summary>File has been successfully migrated and verified.</summary>
    Success = 2,

    /// <summary>File migration failed after exhausting retries.</summary>
    Failed = 3,

    /// <summary>File is queued for retry after a recoverable failure.</summary>
    RetryPending = 4
}

/// <summary>
/// Result of processing a single batch of file entries.
/// </summary>
public class BatchResult
{
    public int BatchNumber { get; set; }
    public List<FileEntry> Succeeded { get; set; } = new();
    public List<FileEntry> Failed { get; set; } = new();
    public List<FileEntry> Retrying { get; set; } = new();
    public TimeSpan Duration { get; set; }
    public string CommitHash { get; set; } = string.Empty;
    public string DeploymentId { get; set; } = string.Empty;

    public int TotalProcessed => Succeeded.Count + Failed.Count + Retrying.Count;
    public bool AllSucceeded => Failed.Count == 0 && Retrying.Count == 0;
}

/// <summary>
/// Comprehensive report of the entire migration run.
/// </summary>
public class MigrationReport
{
    public DateTime GeneratedAt { get; set; } = DateTime.UtcNow;
    public int TotalFiles { get; set; }
    public int Succeeded { get; set; }
    public int Failed { get; set; }
    public int Pending { get; set; }
    public int InProgress { get; set; }
    public int RetryPending { get; set; }
    public TimeSpan TotalDuration { get; set; }
    public List<FileEntry> FailedEntries { get; set; } = new();
    public List<BatchResult> BatchResults { get; set; } = new();

    public double SuccessRate => TotalFiles > 0 ? (double)Succeeded / TotalFiles * 100 : 0;

    public string ToSummary()
    {
        return $"""
            Migration Report - {GeneratedAt:yyyy-MM-dd HH:mm:ss UTC}
            ============================================
            Total Files:    {TotalFiles}
            Succeeded:      {Succeeded} ({SuccessRate:F1}%)
            Failed:         {Failed}
            Pending:        {Pending}
            In Progress:    {InProgress}
            Retry Pending:  {RetryPending}
            Duration:       {TotalDuration}
            Batches:        {BatchResults.Count}
            """;
    }
}

/// <summary>
/// Result of a CI/CD build workflow run.
/// </summary>
public class BuildResult
{
    public bool Success { get; set; }
    public string RunId { get; set; } = string.Empty;
    public string Conclusion { get; set; } = string.Empty;
    public string LogOutput { get; set; } = string.Empty;
    public string Url { get; set; } = string.Empty;
}

/// <summary>
/// Result of a deployment operation.
/// </summary>
public class DeploymentResult
{
    public bool Success { get; set; }
    public string DeploymentId { get; set; } = string.Empty;
    public string Status { get; set; } = string.Empty;
    public string ErrorMessage { get; set; } = string.Empty;
}

/// <summary>
/// Result of a Datadog log query for post-deployment verification.
/// </summary>
public class LogQueryResult
{
    public bool HasErrors { get; set; }
    public int TotalLogEntries { get; set; }
    public int ErrorCount { get; set; }
    public int WarningCount { get; set; }
    public List<string> ErrorMessages { get; set; } = new();
    public List<string> WarningMessages { get; set; } = new();
    public bool FileProcessedSuccessfully { get; set; }
}

/// <summary>
/// Result of the diagnostic engine analysis.
/// </summary>
public class DiagnosticResult
{
    public string Analysis { get; set; } = string.Empty;
    public List<string> SuggestedChanges { get; set; } = new();
    public string RevisedConfig { get; set; } = string.Empty;
    public bool IsRecoverable { get; set; }
    public string RootCause { get; set; } = string.Empty;
}
