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
    /// <param name="version">The version or commit hash to deploy.</param>
    /// <param name="environment">The target environment (e.g., "production", "staging").</param>
    /// <returns>Deployment result with the deployment ID for tracking.</returns>
    Task<DeploymentResult> TriggerDeploymentAsync(string version, string environment);

    /// <summary>
    /// Waits for a deployment to reach a terminal state (success or failure).
    /// </summary>
    /// <param name="deploymentId">The deployment ID to monitor.</param>
    /// <param name="timeout">Maximum time to wait for the deployment to complete.</param>
    /// <returns>Deployment result with final status.</returns>
    Task<DeploymentResult> WaitForDeploymentAsync(string deploymentId, TimeSpan timeout);
}
