using FluentAssertions;
using FtpAgent.Config;
using Xunit;

namespace FtpAgent.Tests;

/// <summary>
/// Tests for ConfigTranslator static helper methods.
/// </summary>
public class ConfigTranslatorTests
{
    [Fact]
    public void ExtractConfigBlock_ExtractsJsonFromMarkdownFences()
    {
        var response = """
            Here is the translated config:

            ```json
            {"host": "sftp.example.com", "port": 22}
            ```

            That should work.
            """;

        var result = ConfigTranslator.ExtractConfigBlock(response);

        result.Should().Contain("sftp.example.com");
        result.Should().NotContain("```");
        result.Should().NotContain("Here is");
    }

    [Fact]
    public void ExtractConfigBlock_ExtractsFromGenericFences()
    {
        var response = "```\n{\"name\": \"test\"}\n```";

        var result = ConfigTranslator.ExtractConfigBlock(response);

        result.Should().Be("{\"name\": \"test\"}");
    }

    [Fact]
    public void ExtractConfigBlock_ReturnsFullResponse_WhenNoFences()
    {
        var response = "{\"host\": \"sftp.example.com\"}";

        var result = ConfigTranslator.ExtractConfigBlock(response);

        result.Should().Be(response);
    }

    [Fact]
    public void ExtractConfigBlock_HandlesEmptyInput()
    {
        var result = ConfigTranslator.ExtractConfigBlock("");
        result.Should().BeEmpty();
    }

    [Fact]
    public void ExtractConfigBlock_TakesFirstBlockOnly()
    {
        var response = "```json\n{\"first\": true}\n```\n\n```json\n{\"second\": true}\n```";

        var result = ConfigTranslator.ExtractConfigBlock(response);

        result.Should().Contain("first");
        result.Should().NotContain("second");
    }
}
