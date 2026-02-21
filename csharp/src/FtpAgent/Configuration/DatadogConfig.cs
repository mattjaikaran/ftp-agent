namespace FtpAgent.Configuration;

/// <summary>
/// Configuration for Datadog integration.
/// </summary>
public class DatadogConfig
{
    public string ApiUrl { get; set; } = "https://api.datadoghq.com";
    public string ApiKey { get; set; } = string.Empty;
    public string AppKey { get; set; } = string.Empty;
    public string ServiceName { get; set; } = string.Empty;
    public string Environment { get; set; } = string.Empty;
}
