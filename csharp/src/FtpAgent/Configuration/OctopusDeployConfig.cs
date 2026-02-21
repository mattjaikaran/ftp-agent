namespace FtpAgent.Configuration;

/// <summary>
/// Configuration for Octopus Deploy integration.
/// </summary>
public class OctopusDeployConfig
{
    public string ServerUrl { get; set; } = string.Empty;
    public string ApiKey { get; set; } = string.Empty;
    public string ProjectName { get; set; } = string.Empty;
    public string EnvironmentName { get; set; } = string.Empty;
    public string SpaceId { get; set; } = "Spaces-1";
}
