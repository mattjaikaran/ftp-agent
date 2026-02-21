namespace FtpAgent.Configuration;

/// <summary>
/// Configuration for GitHub integration.
/// </summary>
public class GitHubConfig
{
    public string Repository { get; set; } = string.Empty;
    public string BaseBranch { get; set; } = "main";
    public string WorkflowName { get; set; } = string.Empty;
    public string TargetRepoPath { get; set; } = string.Empty;
}
