namespace FtpAgent.Configuration;

/// <summary>
/// Marker record for dependency injection to indicate dry-run mode.
/// </summary>
public record DryRunFlag(bool Enabled);
