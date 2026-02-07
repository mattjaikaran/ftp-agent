using FluentAssertions;
using FtpAgent.Orchestration;
using FtpAgent.State;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Xunit;

namespace FtpAgent.Tests;

/// <summary>
/// Integration tests for StateStore using in-memory SQLite.
/// </summary>
public class StateStoreTests : IAsyncDisposable
{
    private readonly StateStore _store;

    public StateStoreTests()
    {
        var config = Options.Create(new AgentConfig
        {
            StateDatabasePath = ":memory:"
        });
        _store = new StateStore(NullLogger<StateStore>.Instance, config);
    }

    public async ValueTask DisposeAsync()
    {
        await _store.DisposeAsync();
    }

    [Fact]
    public async Task InitializeAsync_CreatesSchemaSuccessfully()
    {
        await _store.InitializeAsync();
        var hasPending = await _store.HasPendingFiles();
        hasPending.Should().BeFalse();
    }

    [Fact]
    public async Task LoadEntriesAsync_InsertsNewEntries()
    {
        await _store.InitializeAsync();

        var entries = new List<FileEntry>
        {
            new() { Id = "f1", Name = "file1.csv", LegacyConfig = "host=a" },
            new() { Id = "f2", Name = "file2.csv", LegacyConfig = "host=b" }
        };

        var inserted = await _store.LoadEntriesAsync(entries);

        inserted.Should().Be(2);
        (await _store.HasPendingFiles()).Should().BeTrue();
    }

    [Fact]
    public async Task LoadEntriesAsync_IsIdempotent_SkipsDuplicates()
    {
        await _store.InitializeAsync();

        var entries = new List<FileEntry>
        {
            new() { Id = "f1", Name = "file1.csv", LegacyConfig = "host=a" }
        };

        await _store.LoadEntriesAsync(entries);
        var secondInsert = await _store.LoadEntriesAsync(entries);

        secondInsert.Should().Be(0);
    }

    [Fact]
    public async Task GetNextBatch_ReturnsCorrectBatchSize()
    {
        await _store.InitializeAsync();

        var entries = Enumerable.Range(1, 20).Select(i => new FileEntry
        {
            Id = $"f{i}", Name = $"file{i}.csv", LegacyConfig = $"host=server{i}"
        }).ToList();

        await _store.LoadEntriesAsync(entries);

        var batch = await _store.GetNextBatch(5);
        batch.Should().HaveCount(5);
    }

    [Fact]
    public async Task GetNextBatch_PrioritizesRetryPendingOverPending()
    {
        await _store.InitializeAsync();

        var entries = new List<FileEntry>
        {
            new() { Id = "pending1", Name = "pending.csv", LegacyConfig = "a" },
            new() { Id = "retry1", Name = "retry.csv", LegacyConfig = "b" }
        };

        await _store.LoadEntriesAsync(entries);
        await _store.MarkInProgress("retry1");
        await _store.IncrementRetry("retry1", "some error");

        var batch = await _store.GetNextBatch(10);
        batch.Should().HaveCount(2);
        batch[0].Id.Should().Be("retry1");
    }

    [Fact]
    public async Task MarkInProgress_UpdatesStatus()
    {
        await _store.InitializeAsync();
        await _store.LoadEntriesAsync(new List<FileEntry>
        {
            new() { Id = "f1", Name = "test.csv", LegacyConfig = "x" }
        });

        await _store.MarkInProgress("f1");

        var entry = await _store.GetEntryAsync("f1");
        entry.Should().NotBeNull();
        entry!.Status.Should().Be(MigrationStatus.InProgress);
    }

    [Fact]
    public async Task MarkSuccess_UpdatesStatus()
    {
        await _store.InitializeAsync();
        await _store.LoadEntriesAsync(new List<FileEntry>
        {
            new() { Id = "f1", Name = "test.csv", LegacyConfig = "x" }
        });

        await _store.MarkSuccess("f1");

        var entry = await _store.GetEntryAsync("f1");
        entry!.Status.Should().Be(MigrationStatus.Success);
    }

    [Fact]
    public async Task MarkFailed_SetsStatusAndError()
    {
        await _store.InitializeAsync();
        await _store.LoadEntriesAsync(new List<FileEntry>
        {
            new() { Id = "f1", Name = "test.csv", LegacyConfig = "x" }
        });

        await _store.MarkFailed("f1", "Connection refused");

        var entry = await _store.GetEntryAsync("f1");
        entry!.Status.Should().Be(MigrationStatus.Failed);
        entry.LastError.Should().Be("Connection refused");
    }

    [Fact]
    public async Task IncrementRetry_IncrementsCountAndSetsRetryPending()
    {
        await _store.InitializeAsync();
        await _store.LoadEntriesAsync(new List<FileEntry>
        {
            new() { Id = "f1", Name = "test.csv", LegacyConfig = "x" }
        });

        await _store.IncrementRetry("f1", "error1");
        await _store.IncrementRetry("f1", "error2");

        var entry = await _store.GetEntryAsync("f1");
        entry!.RetryCount.Should().Be(2);
        entry.Status.Should().Be(MigrationStatus.RetryPending);
        entry.LastError.Should().Be("error2");
    }

    [Fact]
    public async Task UpdateNewConfig_PersistsRevisedConfig()
    {
        await _store.InitializeAsync();
        await _store.LoadEntriesAsync(new List<FileEntry>
        {
            new() { Id = "f1", Name = "test.csv", LegacyConfig = "x" }
        });

        await _store.UpdateNewConfig("f1", "{\"host\": \"new-host.com\"}");

        var entry = await _store.GetEntryAsync("f1");
        entry!.NewConfig.Should().Be("{\"host\": \"new-host.com\"}");
    }

    [Fact]
    public async Task HasPendingFiles_ReturnsFalse_WhenAllSucceeded()
    {
        await _store.InitializeAsync();
        await _store.LoadEntriesAsync(new List<FileEntry>
        {
            new() { Id = "f1", Name = "test.csv", LegacyConfig = "x" }
        });

        await _store.MarkSuccess("f1");

        (await _store.HasPendingFiles()).Should().BeFalse();
    }

    [Fact]
    public async Task HasPendingFiles_ReturnsTrue_WhenRetryPending()
    {
        await _store.InitializeAsync();
        await _store.LoadEntriesAsync(new List<FileEntry>
        {
            new() { Id = "f1", Name = "test.csv", LegacyConfig = "x" }
        });

        await _store.IncrementRetry("f1", "error");

        (await _store.HasPendingFiles()).Should().BeTrue();
    }

    [Fact]
    public async Task GenerateReport_ReturnsAccurateCounts()
    {
        await _store.InitializeAsync();
        await _store.LoadEntriesAsync(new List<FileEntry>
        {
            new() { Id = "f1", Name = "s1.csv", LegacyConfig = "a" },
            new() { Id = "f2", Name = "s2.csv", LegacyConfig = "b" },
            new() { Id = "f3", Name = "f1.csv", LegacyConfig = "c" },
            new() { Id = "f4", Name = "p1.csv", LegacyConfig = "d" }
        });

        await _store.MarkSuccess("f1");
        await _store.MarkSuccess("f2");
        await _store.MarkFailed("f3", "permanent failure");

        var report = await _store.GenerateReport();

        report.TotalFiles.Should().Be(4);
        report.Succeeded.Should().Be(2);
        report.Failed.Should().Be(1);
        report.Pending.Should().Be(1);
        report.FailedEntries.Should().HaveCount(1);
        report.FailedEntries[0].Id.Should().Be("f3");
    }

    [Fact]
    public async Task GetEntryAsync_ReturnsNull_WhenNotFound()
    {
        await _store.InitializeAsync();

        var entry = await _store.GetEntryAsync("nonexistent");
        entry.Should().BeNull();
    }
}
