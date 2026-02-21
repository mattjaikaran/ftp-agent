using FtpAgent.Orchestration;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace FtpAgent.State;

/// <summary>
/// SQLite-backed persistence layer for migration state.
/// Tracks the status of every file entry through the migration pipeline,
/// enabling safe resume after crashes and accurate reporting.
/// </summary>
public class StateStore : IAsyncDisposable
{
    private readonly ILogger<StateStore> _logger;
    private readonly string _connectionString;
    private SqliteConnection? _connection;

    public StateStore(
        ILogger<StateStore> logger,
        IOptions<AgentConfig> config)
    {
        _logger = logger;
        var dbPath = config.Value.StateDatabasePath;
        _connectionString = $"Data Source={dbPath}";
    }

    /// <summary>
    /// Initializes the database connection and creates the schema if it does not exist.
    /// </summary>
    public async Task InitializeAsync()
    {
        _logger.LogInformation("Initializing state store: {ConnectionString}", _connectionString);

        _connection = new SqliteConnection(_connectionString);
        await _connection.OpenAsync();

        await ExecuteNonQueryAsync("""
            CREATE TABLE IF NOT EXISTS file_entries (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                legacy_config TEXT NOT NULL,
                new_config TEXT DEFAULT '',
                status INTEGER NOT NULL DEFAULT 0,
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                commit_hash TEXT DEFAULT '',
                deployment_id TEXT DEFAULT '',
                source_path TEXT DEFAULT '',
                destination_path TEXT DEFAULT '',
                protocol TEXT DEFAULT ''
            )
            """);

        await ExecuteNonQueryAsync("""
            CREATE INDEX IF NOT EXISTS idx_file_entries_status ON file_entries(status)
            """);

        var count = await ExecuteScalarAsync<long>("SELECT COUNT(*) FROM file_entries");
        _logger.LogInformation("State store initialized. {Count} existing entries found.", count);
    }

    /// <summary>
    /// Loads a batch of file entries from external source (e.g., parsed CSV) into the state store.
    /// Only inserts entries that do not already exist (idempotent).
    /// </summary>
    public async Task<int> LoadEntriesAsync(List<FileEntry> entries)
    {
        var inserted = 0;

        foreach (var entry in entries)
        {
            var exists = await ExecuteScalarAsync<long>(
                "SELECT COUNT(*) FROM file_entries WHERE id = @id",
                ("@id", entry.Id));

            if (exists > 0)
            {
                _logger.LogDebug("Entry {Id} already exists, skipping", entry.Id);
                continue;
            }

            await ExecuteNonQueryAsync("""
                INSERT INTO file_entries (id, name, legacy_config, new_config, status, retry_count,
                    last_error, source_path, destination_path, protocol)
                VALUES (@id, @name, @legacyConfig, @newConfig, @status, @retryCount,
                    @lastError, @sourcePath, @destPath, @protocol)
                """,
                ("@id", entry.Id),
                ("@name", entry.Name),
                ("@legacyConfig", entry.LegacyConfig),
                ("@newConfig", entry.NewConfig),
                ("@status", (int)entry.Status),
                ("@retryCount", entry.RetryCount),
                ("@lastError", entry.LastError),
                ("@sourcePath", entry.SourcePath),
                ("@destPath", entry.DestinationPath),
                ("@protocol", entry.Protocol));

            inserted++;
        }

        _logger.LogInformation("Loaded {Inserted} new entries ({Skipped} already existed)",
            inserted, entries.Count - inserted);

        return inserted;
    }

    /// <summary>
    /// Returns true if there are files in Pending or RetryPending status.
    /// </summary>
    public async Task<bool> HasPendingFiles()
    {
        var count = await ExecuteScalarAsync<long>(
            "SELECT COUNT(*) FROM file_entries WHERE status IN (@pending, @retry)",
            ("@pending", (int)MigrationStatus.Pending),
            ("@retry", (int)MigrationStatus.RetryPending));

        return count > 0;
    }

    /// <summary>
    /// Gets the next batch of files to process, preferring RetryPending over Pending.
    /// </summary>
    public async Task<List<FileEntry>> GetNextBatch(int size)
    {
        EnsureConnected();

        var entries = new List<FileEntry>();

        // Prioritize retries, then pending
        using var command = _connection!.CreateCommand();
        command.CommandText = """
            SELECT id, name, legacy_config, new_config, status, retry_count, last_error,
                   source_path, destination_path, protocol, commit_hash, deployment_id,
                   created_at, updated_at
            FROM file_entries
            WHERE status IN (@pending, @retry)
            ORDER BY
                CASE WHEN status = @retry THEN 0 ELSE 1 END,
                created_at ASC
            LIMIT @limit
            """;

        command.Parameters.AddWithValue("@pending", (int)MigrationStatus.Pending);
        command.Parameters.AddWithValue("@retry", (int)MigrationStatus.RetryPending);
        command.Parameters.AddWithValue("@limit", size);

        using var reader = await command.ExecuteReaderAsync();
        while (await reader.ReadAsync())
        {
            entries.Add(MapReaderToFileEntry(reader));
        }

        _logger.LogDebug("Retrieved batch of {Count} entries", entries.Count);
        return entries;
    }

    /// <summary>
    /// Marks a file entry as in-progress.
    /// </summary>
    public async Task MarkInProgress(string id)
    {
        await UpdateStatus(id, MigrationStatus.InProgress);
    }

    /// <summary>
    /// Marks a file entry as successfully migrated.
    /// </summary>
    public async Task MarkSuccess(string id)
    {
        await UpdateStatus(id, MigrationStatus.Success);
    }

    /// <summary>
    /// Marks a file entry as permanently failed.
    /// </summary>
    public async Task MarkFailed(string id, string error)
    {
        await ExecuteNonQueryAsync("""
            UPDATE file_entries
            SET status = @status, last_error = @error, updated_at = datetime('now')
            WHERE id = @id
            """,
            ("@id", id),
            ("@status", (int)MigrationStatus.Failed),
            ("@error", error));
    }

    /// <summary>
    /// Increments the retry count and queues the file for re-processing.
    /// If max retries are exceeded, the caller is responsible for calling MarkFailed.
    /// </summary>
    public async Task IncrementRetry(string id, string error)
    {
        await ExecuteNonQueryAsync("""
            UPDATE file_entries
            SET status = @status, retry_count = retry_count + 1,
                last_error = @error, updated_at = datetime('now')
            WHERE id = @id
            """,
            ("@id", id),
            ("@status", (int)MigrationStatus.RetryPending),
            ("@error", error));
    }

    /// <summary>
    /// Updates the translated config for a file entry.
    /// </summary>
    public async Task UpdateNewConfig(string id, string newConfig)
    {
        await ExecuteNonQueryAsync("""
            UPDATE file_entries
            SET new_config = @config, updated_at = datetime('now')
            WHERE id = @id
            """,
            ("@id", id),
            ("@config", newConfig));
    }

    /// <summary>
    /// Generates a comprehensive migration report from the current state.
    /// </summary>
    public async Task<MigrationReport> GenerateReport()
    {
        EnsureConnected();

        var report = new MigrationReport();

        report.TotalFiles = (int)await ExecuteScalarAsync<long>("SELECT COUNT(*) FROM file_entries");
        report.Succeeded = (int)await ExecuteScalarAsync<long>(
            "SELECT COUNT(*) FROM file_entries WHERE status = @s", ("@s", (int)MigrationStatus.Success));
        report.Failed = (int)await ExecuteScalarAsync<long>(
            "SELECT COUNT(*) FROM file_entries WHERE status = @s", ("@s", (int)MigrationStatus.Failed));
        report.Pending = (int)await ExecuteScalarAsync<long>(
            "SELECT COUNT(*) FROM file_entries WHERE status = @s", ("@s", (int)MigrationStatus.Pending));
        report.InProgress = (int)await ExecuteScalarAsync<long>(
            "SELECT COUNT(*) FROM file_entries WHERE status = @s", ("@s", (int)MigrationStatus.InProgress));
        report.RetryPending = (int)await ExecuteScalarAsync<long>(
            "SELECT COUNT(*) FROM file_entries WHERE status = @s", ("@s", (int)MigrationStatus.RetryPending));

        // Load failed entries for the report
        using var command = _connection!.CreateCommand();
        command.CommandText = "SELECT * FROM file_entries WHERE status = @s";
        command.Parameters.AddWithValue("@s", (int)MigrationStatus.Failed);

        using var reader = await command.ExecuteReaderAsync();
        while (await reader.ReadAsync())
        {
            report.FailedEntries.Add(MapReaderToFileEntry(reader));
        }

        _logger.LogInformation("Report generated: {Summary}", report.ToSummary());
        return report;
    }

    /// <summary>
    /// Gets a single file entry by ID.
    /// </summary>
    public async Task<FileEntry?> GetEntryAsync(string id)
    {
        EnsureConnected();

        using var command = _connection!.CreateCommand();
        command.CommandText = "SELECT * FROM file_entries WHERE id = @id";
        command.Parameters.AddWithValue("@id", id);

        using var reader = await command.ExecuteReaderAsync();
        if (await reader.ReadAsync())
        {
            return MapReaderToFileEntry(reader);
        }

        return null;
    }

    private async Task UpdateStatus(string id, MigrationStatus status)
    {
        await ExecuteNonQueryAsync("""
            UPDATE file_entries
            SET status = @status, updated_at = datetime('now')
            WHERE id = @id
            """,
            ("@id", id),
            ("@status", (int)status));
    }

    private static FileEntry MapReaderToFileEntry(SqliteDataReader reader)
    {
        return new FileEntry
        {
            Id = reader.GetString(reader.GetOrdinal("id")),
            Name = reader.GetString(reader.GetOrdinal("name")),
            LegacyConfig = reader.GetString(reader.GetOrdinal("legacy_config")),
            NewConfig = reader.IsDBNull(reader.GetOrdinal("new_config"))
                ? string.Empty : reader.GetString(reader.GetOrdinal("new_config")),
            Status = (MigrationStatus)reader.GetInt32(reader.GetOrdinal("status")),
            RetryCount = reader.GetInt32(reader.GetOrdinal("retry_count")),
            LastError = reader.IsDBNull(reader.GetOrdinal("last_error"))
                ? string.Empty : reader.GetString(reader.GetOrdinal("last_error")),
            SourcePath = reader.IsDBNull(reader.GetOrdinal("source_path"))
                ? string.Empty : reader.GetString(reader.GetOrdinal("source_path")),
            DestinationPath = reader.IsDBNull(reader.GetOrdinal("destination_path"))
                ? string.Empty : reader.GetString(reader.GetOrdinal("destination_path")),
            Protocol = reader.IsDBNull(reader.GetOrdinal("protocol"))
                ? string.Empty : reader.GetString(reader.GetOrdinal("protocol")),
            CommitHash = reader.IsDBNull(reader.GetOrdinal("commit_hash"))
                ? string.Empty : reader.GetString(reader.GetOrdinal("commit_hash")),
            DeploymentId = reader.IsDBNull(reader.GetOrdinal("deployment_id"))
                ? string.Empty : reader.GetString(reader.GetOrdinal("deployment_id"))
        };
    }

    private async Task ExecuteNonQueryAsync(string sql, params (string name, object value)[] parameters)
    {
        EnsureConnected();

        using var command = _connection!.CreateCommand();
        command.CommandText = sql;

        foreach (var (name, value) in parameters)
        {
            command.Parameters.AddWithValue(name, value);
        }

        await command.ExecuteNonQueryAsync();
    }

    private async Task<T> ExecuteScalarAsync<T>(string sql, params (string name, object value)[] parameters)
    {
        EnsureConnected();

        using var command = _connection!.CreateCommand();
        command.CommandText = sql;

        foreach (var (name, value) in parameters)
        {
            command.Parameters.AddWithValue(name, value);
        }

        var result = await command.ExecuteScalarAsync();
        return (T)(result ?? default(T)!);
    }

    private void EnsureConnected()
    {
        if (_connection is null)
        {
            throw new InvalidOperationException(
                "StateStore has not been initialized. Call InitializeAsync() first.");
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_connection is not null)
        {
            await _connection.DisposeAsync();
            _connection = null;
        }
    }
}
