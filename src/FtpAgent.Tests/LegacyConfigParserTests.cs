using FluentAssertions;
using FtpAgent.Config;
using FtpAgent.State;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace FtpAgent.Tests;

/// <summary>
/// Tests for LegacyConfigParser CSV and text parsing.
/// </summary>
public class LegacyConfigParserTests : IDisposable
{
    private readonly LegacyConfigParser _parser;
    private readonly string _tempDir;

    public LegacyConfigParserTests()
    {
        _parser = new LegacyConfigParser(NullLogger<LegacyConfigParser>.Instance);
        _tempDir = Path.Combine(Path.GetTempPath(), $"ftp-agent-test-{Guid.NewGuid():N}");
        Directory.CreateDirectory(_tempDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
        {
            Directory.Delete(_tempDir, recursive: true);
        }
    }

    [Fact]
    public async Task ParseFromFileAsync_ParsesValidCsv()
    {
        var csv = "id,name,config,protocol\nf1,daily-report,host=sftp.example.com,SFTP\nf2,weekly-data,host=ftp.vendor.com,FTP";
        var filePath = Path.Combine(_tempDir, "test.csv");
        await File.WriteAllTextAsync(filePath, csv);

        var entries = await _parser.ParseFromFileAsync(filePath);

        entries.Should().HaveCount(2);
        entries[0].Id.Should().Be("f1");
        entries[0].Name.Should().Be("daily-report");
        entries[0].Protocol.Should().Be("SFTP");
        entries[1].Id.Should().Be("f2");
        entries[1].Protocol.Should().Be("FTP");
    }

    [Fact]
    public async Task ParseFromFileAsync_HandlesQuotedFieldsWithCommas()
    {
        var csv = "id,name,config\nf1,\"report, daily\",\"host=a,port=22\"";
        var filePath = Path.Combine(_tempDir, "quoted.csv");
        await File.WriteAllTextAsync(filePath, csv);

        var entries = await _parser.ParseFromFileAsync(filePath);

        entries.Should().HaveCount(1);
        entries[0].Name.Should().Be("report, daily");
    }

    [Fact]
    public async Task ParseFromFileAsync_AcceptsAlternativeColumnNames()
    {
        var csv = "file_id,filename,configuration\nABC,test-file,host=sftp.test.com";
        var filePath = Path.Combine(_tempDir, "alt.csv");
        await File.WriteAllTextAsync(filePath, csv);

        var entries = await _parser.ParseFromFileAsync(filePath);

        entries.Should().HaveCount(1);
        entries[0].Id.Should().Be("ABC");
        entries[0].Name.Should().Be("test-file");
    }

    [Fact]
    public async Task ParseFromFileAsync_ThrowsOnMissingFile()
    {
        var act = () => _parser.ParseFromFileAsync("/nonexistent/path.csv");
        await act.Should().ThrowAsync<FileNotFoundException>();
    }

    [Fact]
    public async Task ParseFromFileAsync_ThrowsOnHeaderOnlyFile()
    {
        var csv = "id,name,config";
        var filePath = Path.Combine(_tempDir, "headeronly.csv");
        await File.WriteAllTextAsync(filePath, csv);

        var act = () => _parser.ParseFromFileAsync(filePath);
        await act.Should().ThrowAsync<InvalidDataException>();
    }

    [Fact]
    public async Task ParseFromFileAsync_SkipsBlankLines()
    {
        var csv = "id,name,config\nf1,file1,a\n\nf2,file2,b\n\n";
        var filePath = Path.Combine(_tempDir, "blanks.csv");
        await File.WriteAllTextAsync(filePath, csv);

        var entries = await _parser.ParseFromFileAsync(filePath);
        entries.Should().HaveCount(2);
    }

    [Fact]
    public async Task ParseFromFileAsync_GeneratesIdWhenMissing()
    {
        var csv = "id,name,config\n,unnamed-file,host=x";
        var filePath = Path.Combine(_tempDir, "noid.csv");
        await File.WriteAllTextAsync(filePath, csv);

        var entries = await _parser.ParseFromFileAsync(filePath);
        entries[0].Id.Should().StartWith("file-");
    }

    [Fact]
    public void ParseFromText_SplitsByBlankLines()
    {
        var text = "id=f1\nname=file1\nprotocol=SFTP\n\nid=f2\nname=file2\nprotocol=FTP";

        var entries = _parser.ParseFromText(text);

        entries.Should().HaveCount(2);
        entries[0].Name.Should().Be("file1");
        entries[1].Name.Should().Be("file2");
    }

    [Fact]
    public void ParseFromText_DetectsProtocol()
    {
        var text = "id=f1\nname=exchange-file\nserver=mail.company.com\ntype=EWS";

        var entries = _parser.ParseFromText(text);

        entries.Should().HaveCount(1);
        // DetectProtocol should match "ews" to Exchange
        entries[0].Protocol.Should().NotBeEmpty();
    }

    [Fact]
    public void ParseFromText_HandlesIniStyleSections()
    {
        var text = "[server1]\nid=f1\nname=s1\nprotocol=SFTP\n[server2]\nid=f2\nname=s2\nprotocol=FTP";

        var entries = _parser.ParseFromText(text);
        entries.Should().HaveCountGreaterOrEqualTo(2);
    }
}
