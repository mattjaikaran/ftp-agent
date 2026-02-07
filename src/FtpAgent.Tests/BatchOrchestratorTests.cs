using FluentAssertions;
using FtpAgent.CI;
using FtpAgent.Config;
using FtpAgent.Deployment;
using FtpAgent.Diagnostics;
using FtpAgent.Git;
using FtpAgent.Monitoring;
using FtpAgent.Orchestration;
using FtpAgent.State;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;

namespace FtpAgent.Tests;

public class BatchOrchestratorTests
{
    private readonly Mock<ILogger<BatchOrchestrator>> _loggerMock;
    private readonly Mock<IOptions<AgentConfig>> _configMock;
    private readonly Mock<ConfigTranslator> _translatorMock;
    private readonly Mock<NewConfigWriter> _writerMock;
    private readonly Mock<GitManager> _gitManagerMock;
    private readonly Mock<GitHubActionsMonitor> _ciMonitorMock;
    private readonly Mock<IDeploymentClient> _deploymentClientMock;
    private readonly Mock<DatadogClient> _datadogClientMock;
    private readonly Mock<DiagnosticEngine> _diagnosticEngineMock;
    private readonly Mock<StateStore> _stateStoreMock;

    public BatchOrchestratorTests()
    {
        _loggerMock = new Mock<ILogger<BatchOrchestrator>>();
        _configMock = new Mock<IOptions<AgentConfig>>();
        _translatorMock = new Mock<ConfigTranslator>(
            Mock.Of<ILogger<ConfigTranslator>>(),
            Options.Create(new CopilotConfig()));
        _writerMock = new Mock<NewConfigWriter>(
            Mock.Of<ILogger<NewConfigWriter>>(),
            Options.Create(new GitHubConfig()));
        _gitManagerMock = new Mock<GitManager>(
            Mock.Of<ILogger<GitManager>>(),
            Options.Create(new GitHubConfig()));
        _ciMonitorMock = new Mock<GitHubActionsMonitor>(
            Mock.Of<ILogger<GitHubActionsMonitor>>(),
            Options.Create(new GitHubConfig()),
            Options.Create(new AgentConfig()));
        _deploymentClientMock = new Mock<IDeploymentClient>();
        _datadogClientMock = new Mock<DatadogClient>(
            Mock.Of<ILogger<DatadogClient>>(),
            Mock.Of<IHttpClientFactory>(),
            Options.Create(new DatadogConfig()));
        _diagnosticEngineMock = new Mock<DiagnosticEngine>(
            Mock.Of<ILogger<DiagnosticEngine>>(),
            Options.Create(new CopilotConfig()));
        _stateStoreMock = new Mock<StateStore>(
            Mock.Of<ILogger<StateStore>>(),
            Options.Create(new AgentConfig()));
    }

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
    public void DryRunFlag_SetsEnabledCorrectly()
    {
        var enabled = new DryRunFlag(true);
        var disabled = new DryRunFlag(false);

        enabled.Enabled.Should().BeTrue();
        disabled.Enabled.Should().BeFalse();
    }

    // TODO: Add integration tests that exercise the full orchestrator pipeline
    // with mocked external dependencies (Copilot CLI, git, gh, Octopus, Datadog).

    // TODO: Add tests for LegacyConfigParser with sample CSV input.

    // TODO: Add tests for StateStore using an in-memory SQLite database.

    // TODO: Add tests for ConfigTranslator response parsing (code fence extraction).
}
