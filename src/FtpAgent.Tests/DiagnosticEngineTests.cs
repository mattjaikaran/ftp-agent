using FluentAssertions;
using FtpAgent.Diagnostics;
using Xunit;

namespace FtpAgent.Tests;

/// <summary>
/// Tests for DiagnosticEngine response parsing logic.
/// </summary>
public class DiagnosticEngineParsingTests
{
    [Fact]
    public void ParseDiagnosticResponse_ParsesValidJson()
    {
        var json = """
            {
                "analysis": "Port mismatch detected",
                "rootCause": "Config uses port 21 but server expects 22",
                "isRecoverable": true,
                "suggestedChanges": ["Change port from 21 to 22"],
                "revisedConfig": "{\"port\": 22}"
            }
            """;

        var result = DiagnosticEngine.ParseDiagnosticResponse(json);

        result.Analysis.Should().Contain("Port mismatch");
        result.RootCause.Should().Contain("port 21");
        result.IsRecoverable.Should().BeTrue();
        result.SuggestedChanges.Should().ContainSingle().Which.Should().Contain("port");
        result.RevisedConfig.Should().Contain("22");
    }

    [Fact]
    public void ParseDiagnosticResponse_HandlesRevisedConfigAsObject()
    {
        var json = """
            {
                "analysis": "test",
                "rootCause": "test",
                "isRecoverable": true,
                "suggestedChanges": [],
                "revisedConfig": {"host": "new-host.com", "port": 22}
            }
            """;

        var result = DiagnosticEngine.ParseDiagnosticResponse(json);

        result.RevisedConfig.Should().Contain("new-host.com");
    }

    [Fact]
    public void ParseDiagnosticResponse_FallsBackToTextParsing()
    {
        var text = """
            Root cause: The SSH key format is incompatible.

            This issue is recoverable by updating the key format.

            ```json
            {"host": "sftp.example.com", "keyFormat": "ed25519"}
            ```
            """;

        var result = DiagnosticEngine.ParseDiagnosticResponse(text);

        result.RootCause.Should().Contain("SSH key format");
        result.IsRecoverable.Should().BeTrue();
        result.RevisedConfig.Should().Contain("ed25519");
    }

    [Fact]
    public void ParseDiagnosticResponse_DetectsRecoverableFromText()
    {
        var text = "The issue can be fixed by updating the port number.";

        var result = DiagnosticEngine.ParseDiagnosticResponse(text);

        result.IsRecoverable.Should().BeTrue();
    }

    [Fact]
    public void ParseDiagnosticResponse_NonRecoverable_WhenNoKeywords()
    {
        var text = "The server is permanently offline. Manual vendor coordination required.";

        var result = DiagnosticEngine.ParseDiagnosticResponse(text);

        result.IsRecoverable.Should().BeFalse();
    }

    [Fact]
    public void ParseDiagnosticResponse_HandlesEmptyJson()
    {
        var json = "{}";

        var result = DiagnosticEngine.ParseDiagnosticResponse(json);

        result.Analysis.Should().BeEmpty();
        result.IsRecoverable.Should().BeFalse();
        result.SuggestedChanges.Should().BeEmpty();
    }

    [Fact]
    public void ParseDiagnosticResponse_SkipsNullSuggestedChanges()
    {
        var json = """
            {
                "analysis": "test",
                "suggestedChanges": [null, "valid change", null]
            }
            """;

        var result = DiagnosticEngine.ParseDiagnosticResponse(json);

        result.SuggestedChanges.Should().ContainSingle().Which.Should().Be("valid change");
    }
}
