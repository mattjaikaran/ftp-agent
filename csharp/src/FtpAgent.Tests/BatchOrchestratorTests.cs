using FluentAssertions;
using FtpAgent.Configuration;
using FtpAgent.Orchestration;
using FtpAgent.State;
using Xunit;

namespace FtpAgent.Tests;

/// <summary>
/// Tests for AgentConfig default values.
/// </summary>
public class AgentConfigTests
{
    [Fact]
    public void AgentConfig_DefaultValues_AreReasonable()
    {
        var config = new AgentConfig();

        config.BatchSize.Should().Be(10);
        config.MaxRetriesPerFile.Should().Be(3);
        config.DeployWaitTimeoutMinutes.Should().Be(30);
        config.DatadogCheckDelayMinutes.Should().Be(5);
        config.LogQueryWindowMinutes.Should().Be(15);
        config.CiBuildTimeoutMinutes.Should().Be(20);
        config.PollIntervalSeconds.Should().Be(30);
        config.StopOnBatchFailure.Should().BeFalse();
        config.MaxBatchesPerRun.Should().Be(0);
    }

    [Fact]
    public void AgentConfig_CanSetCustomValues()
    {
        var config = new AgentConfig
        {
            BatchSize = 50,
            MaxRetriesPerFile = 5,
            DeployWaitTimeoutMinutes = 60
        };

        config.BatchSize.Should().Be(50);
        config.MaxRetriesPerFile.Should().Be(5);
        config.DeployWaitTimeoutMinutes.Should().Be(60);
    }
}

/// <summary>
/// Tests for FileEntry model.
/// </summary>
public class FileEntryTests
{
    [Fact]
    public void FileEntry_DefaultStatus_IsPending()
    {
        var entry = new FileEntry
        {
            Id = "test-001",
            Name = "test-file.csv"
        };

        entry.Status.Should().Be(MigrationStatus.Pending);
        entry.RetryCount.Should().Be(0);
        entry.LastError.Should().BeEmpty();
    }

    [Fact]
    public void FileEntry_ToString_IncludesIdNameAndStatus()
    {
        var entry = new FileEntry
        {
            Id = "test-001",
            Name = "daily-report.csv",
            Status = MigrationStatus.InProgress
        };

        entry.ToString().Should().Contain("test-001");
        entry.ToString().Should().Contain("daily-report.csv");
        entry.ToString().Should().Contain("InProgress");
    }

    [Fact]
    public void FileEntry_CanSetAllProperties()
    {
        var entry = new FileEntry
        {
            Id = "file-042",
            Name = "vendor-report.dat",
            LegacyConfig = "host=sftp.vendor.com",
            NewConfig = "{\"host\": \"sftp.vendor.com\"}",
            Status = MigrationStatus.Success,
            RetryCount = 2,
            LastError = "previous error",
            Protocol = "SFTP",
            SourcePath = "/outbound/reports",
            DestinationPath = "configs/sftp/vendor-report.json",
            CommitHash = "abc123",
            DeploymentId = "deploy-001"
        };

        entry.Id.Should().Be("file-042");
        entry.Protocol.Should().Be("SFTP");
        entry.CommitHash.Should().Be("abc123");
        entry.DeploymentId.Should().Be("deploy-001");
    }
}

/// <summary>
/// Tests for MigrationReport calculations.
/// </summary>
public class MigrationReportTests
{
    [Fact]
    public void MigrationReport_SuccessRate_CalculatesCorrectly()
    {
        var report = new MigrationReport
        {
            TotalFiles = 100,
            Succeeded = 85,
            Failed = 15
        };

        report.SuccessRate.Should().Be(85.0);
    }

    [Fact]
    public void MigrationReport_SuccessRate_HandlesZeroTotal()
    {
        var report = new MigrationReport
        {
            TotalFiles = 0
        };

        report.SuccessRate.Should().Be(0);
    }

    [Fact]
    public void MigrationReport_ToSummary_ContainsAllFields()
    {
        var report = new MigrationReport
        {
            TotalFiles = 1400,
            Succeeded = 1350,
            Failed = 30,
            Pending = 10,
            InProgress = 5,
            RetryPending = 5
        };

        var summary = report.ToSummary();

        summary.Should().Contain("1400");
        summary.Should().Contain("1350");
        summary.Should().Contain("30");
        summary.Should().Contain("Migration Report");
    }

    [Fact]
    public void MigrationReport_SuccessRate_100Percent()
    {
        var report = new MigrationReport
        {
            TotalFiles = 50,
            Succeeded = 50,
            Failed = 0
        };

        report.SuccessRate.Should().Be(100.0);
    }
}

/// <summary>
/// Tests for BatchResult model.
/// </summary>
public class BatchResultTests
{
    [Fact]
    public void BatchResult_AllSucceeded_TrueWhenNoFailures()
    {
        var result = new BatchResult
        {
            Succeeded = { new FileEntry { Id = "1" }, new FileEntry { Id = "2" } }
        };

        result.AllSucceeded.Should().BeTrue();
        result.TotalProcessed.Should().Be(2);
    }

    [Fact]
    public void BatchResult_AllSucceeded_FalseWhenHasFailures()
    {
        var result = new BatchResult
        {
            Succeeded = { new FileEntry { Id = "1" } },
            Failed = { new FileEntry { Id = "2" } }
        };

        result.AllSucceeded.Should().BeFalse();
        result.TotalProcessed.Should().Be(2);
    }

    [Fact]
    public void BatchResult_Empty_AllSucceededIsTrue()
    {
        var result = new BatchResult();

        result.AllSucceeded.Should().BeTrue();
        result.TotalProcessed.Should().Be(0);
    }
}

/// <summary>
/// Tests for DryRunFlag.
/// </summary>
public class DryRunFlagTests
{
    [Fact]
    public void DryRunFlag_SetsEnabledCorrectly()
    {
        var enabled = new DryRunFlag(true);
        var disabled = new DryRunFlag(false);

        enabled.Enabled.Should().BeTrue();
        disabled.Enabled.Should().BeFalse();
    }
}

/// <summary>
/// Tests for MigrationStatus enum values.
/// </summary>
public class MigrationStatusTests
{
    [Fact]
    public void MigrationStatus_HasExpectedValues()
    {
        ((int)MigrationStatus.Pending).Should().Be(0);
        ((int)MigrationStatus.InProgress).Should().Be(1);
        ((int)MigrationStatus.Success).Should().Be(2);
        ((int)MigrationStatus.Failed).Should().Be(3);
        ((int)MigrationStatus.RetryPending).Should().Be(4);
    }
}

/// <summary>
/// Tests for BuildResult model.
/// </summary>
public class BuildResultTests
{
    [Fact]
    public void BuildResult_Defaults()
    {
        var result = new BuildResult();

        result.Success.Should().BeFalse();
        result.LogOutput.Should().BeEmpty();
    }

    [Fact]
    public void BuildResult_SuccessfulBuild()
    {
        var result = new BuildResult
        {
            Success = true,
            RunId = "12345",
            Conclusion = "success",
            Url = "https://github.com/org/repo/actions/runs/12345"
        };

        result.Success.Should().BeTrue();
        result.Conclusion.Should().Be("success");
    }
}

/// <summary>
/// Tests for DeploymentResult model.
/// </summary>
public class DeploymentResultTests
{
    [Fact]
    public void DeploymentResult_Defaults()
    {
        var result = new DeploymentResult();

        result.Success.Should().BeFalse();
    }

    [Fact]
    public void DeploymentResult_SuccessfulDeployment()
    {
        var result = new DeploymentResult
        {
            Success = true,
            DeploymentId = "deploy-0001",
            Status = "Success"
        };

        result.Success.Should().BeTrue();
        result.DeploymentId.Should().Be("deploy-0001");
    }
}

/// <summary>
/// Tests for LogQueryResult model.
/// </summary>
public class LogQueryResultTests
{
    [Fact]
    public void LogQueryResult_Defaults()
    {
        var result = new LogQueryResult();

        result.HasErrors.Should().BeFalse();
        result.FileProcessedSuccessfully.Should().BeFalse();
        result.ErrorCount.Should().Be(0);
        result.TotalLogEntries.Should().Be(0);
        result.ErrorMessages.Should().BeEmpty();
    }

    [Fact]
    public void LogQueryResult_WithErrors()
    {
        var result = new LogQueryResult
        {
            HasErrors = true,
            ErrorCount = 3,
            TotalLogEntries = 15,
            ErrorMessages = { "ConnectionRefused", "TimeoutException", "AuthFailed" }
        };

        result.HasErrors.Should().BeTrue();
        result.ErrorMessages.Should().HaveCount(3);
    }
}

/// <summary>
/// Tests for DiagnosticResult model.
/// </summary>
public class DiagnosticResultTests
{
    [Fact]
    public void DiagnosticResult_Defaults()
    {
        var result = new DiagnosticResult();

        result.IsRecoverable.Should().BeFalse();
        result.SuggestedChanges.Should().BeEmpty();
    }

    [Fact]
    public void DiagnosticResult_RecoverableIssue()
    {
        var result = new DiagnosticResult
        {
            RootCause = "PGP key path is incorrect",
            Analysis = "Update pgp_key_path to /keys/vendor.asc",
            IsRecoverable = true,
            SuggestedChanges = { "pgp_key_path=/keys/vendor.asc" }
        };

        result.IsRecoverable.Should().BeTrue();
        result.SuggestedChanges.Should().Contain("pgp_key_path=/keys/vendor.asc");
        result.RootCause.Should().Contain("PGP");
    }
}
