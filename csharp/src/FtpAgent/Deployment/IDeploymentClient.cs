using FtpAgent.State;

namespace FtpAgent.Deployment;

/// <summary>
/// Abstraction for deployment operations. Implementations handle specific CD systems
/// (Octopus Deploy, stub for testing, etc.).
/// </summary>
public interface IDeploymentClient
{
    /// <summary>
    /// Triggers a new deployment for the given version to the specified environment.
    /// </summary>
    Task<DeploymentResult> TriggerDeploymentAsync(string version, string environment);

    /// <summary>
    /// Waits for a deployment to reach a terminal state (success or failure).
    /// </summary>
    Task<DeploymentResult> WaitForDeploymentAsync(
        string deploymentId,
        TimeSpan timeout,
        CancellationToken cancellationToken = default);
}
