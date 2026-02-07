namespace FtpAgent.Configuration;

/// <summary>
/// Configuration for GitHub Copilot CLI integration.
/// </summary>
public class CopilotConfig
{
    public string CliPath { get; set; } = "gh";
    public string Model { get; set; } = "claude-opus-4-5-20250514";
    public int TimeoutSeconds { get; set; } = 120;
    public string ConfigTranslationPromptPath { get; set; } = "prompts/config-translation.md";
    public string ErrorDiagnosisPromptPath { get; set; } = "prompts/error-diagnosis.md";
}
