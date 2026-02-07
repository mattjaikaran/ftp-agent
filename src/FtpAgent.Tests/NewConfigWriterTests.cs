using System.Text.Json;
using FluentAssertions;
using FtpAgent.Config;
using FtpAgent.Configuration;
using FtpAgent.State;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Xunit;

namespace FtpAgent.Tests;

/// <summary>
/// Tests for NewConfigWriter path resolution and JSON formatting.
/// </summary>
public class NewConfigWriterTests : IDisposable
{
    private readonly NewConfigWriter _writer;
    private readonly string _tempDir;

    public NewConfigWriterTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"ftp-agent-writer-{Guid.NewGuid():N}");
        Directory.CreateDirectory(_tempDir);

        var config = Options.Create(new GitHubConfig
        {
            TargetRepoPath = _tempDir
        });
        _writer = new NewConfigWriter(NullLogger<NewConfigWriter>.Instance, config);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
        {
            Directory.Delete(_tempDir, recursive: true);
        }
    }

    [Fact]
    public async Task WriteConfigAsync_CreatesFileAtCorrectPath()
    {
        var file = new FileEntry
        {
            Id = "f1",
            Name = "daily-report",
            Protocol = "SFTP",
            NewConfig = "{\"host\": \"sftp.example.com\"}"
        };

        var outputPath = await _writer.WriteConfigAsync(file);

        File.Exists(outputPath).Should().BeTrue();
        outputPath.Should().Contain("configs");
        outputPath.Should().Contain("sftp");
        outputPath.Should().EndWith("daily-report.json");
    }

    [Fact]
    public async Task WriteConfigAsync_FormatsJsonAsPrettyPrint()
    {
        var file = new FileEntry
        {
            Id = "f1",
            Name = "test",
            Protocol = "FTP",
            NewConfig = "{\"host\":\"ftp.test.com\",\"port\":21}"
        };

        var outputPath = await _writer.WriteConfigAsync(file);
        var content = await File.ReadAllTextAsync(outputPath);

        // Pretty-printed JSON should contain newlines
        content.Should().Contain("\n");
        // Verify it's valid JSON
        var act = () => JsonDocument.Parse(content);
        act.Should().NotThrow();
    }

    [Fact]
    public async Task WriteConfigAsync_CreatesDirectoriesAsNeeded()
    {
        var file = new FileEntry
        {
            Id = "f1",
            Name = "vendor-data",
            Protocol = "SFTP",
            NewConfig = "{\"host\": \"sftp.vendor.com\"}"
        };

        var outputPath = await _writer.WriteConfigAsync(file);

        var dir = Path.GetDirectoryName(outputPath);
        Directory.Exists(dir).Should().BeTrue();
    }

    [Fact]
    public async Task WriteConfigAsync_UsesExplicitDestinationPath()
    {
        var file = new FileEntry
        {
            Id = "f1",
            Name = "test",
            Protocol = "SFTP",
            NewConfig = "{\"host\": \"a\"}",
            DestinationPath = "custom/path/my-config.json"
        };

        var outputPath = await _writer.WriteConfigAsync(file);

        outputPath.Should().Contain("custom");
        outputPath.Should().EndWith("my-config.json");
    }

    [Fact]
    public async Task WriteConfigAsync_ThrowsOnEmptyNewConfig()
    {
        var file = new FileEntry
        {
            Id = "f1",
            Name = "test",
            Protocol = "SFTP",
            NewConfig = ""
        };

        var act = () => _writer.WriteConfigAsync(file);
        await act.Should().ThrowAsync<ArgumentException>();
    }

    [Fact]
    public async Task WriteConfigAsync_HandlesNonJsonConfig()
    {
        var file = new FileEntry
        {
            Id = "f1",
            Name = "yaml-file",
            Protocol = "SFTP",
            NewConfig = "host: sftp.example.com\nport: 22"
        };

        var outputPath = await _writer.WriteConfigAsync(file);
        var content = await File.ReadAllTextAsync(outputPath);

        // Should write raw content if not valid JSON
        content.Should().Contain("host: sftp.example.com");
    }

    [Fact]
    public async Task WriteConfigAsync_SanitizesFileNames()
    {
        var file = new FileEntry
        {
            Id = "f1",
            Name = "Vendor Report Daily",
            Protocol = "SFTP",
            NewConfig = "{\"host\": \"a\"}"
        };

        var outputPath = await _writer.WriteConfigAsync(file);

        // Spaces should be replaced with dashes and name lowercased
        var fileName = Path.GetFileNameWithoutExtension(outputPath);
        fileName.Should().NotContain(" ");
        fileName.Should().Be("vendor-report-daily");
    }

    [Fact]
    public async Task WriteConfigAsync_UpdatesFileEntryDestinationPath()
    {
        var file = new FileEntry
        {
            Id = "f1",
            Name = "test",
            Protocol = "FTP",
            NewConfig = "{\"host\": \"a\"}"
        };

        file.DestinationPath.Should().BeEmpty();
        await _writer.WriteConfigAsync(file);
        file.DestinationPath.Should().NotBeEmpty();
    }

    [Fact]
    public async Task WriteConfigAsync_FallsBackToGeneralForUnknownProtocol()
    {
        var file = new FileEntry
        {
            Id = "f1",
            Name = "test",
            Protocol = "Unknown",
            NewConfig = "{\"host\": \"a\"}"
        };

        var outputPath = await _writer.WriteConfigAsync(file);
        outputPath.Should().Contain("general");
    }
}
