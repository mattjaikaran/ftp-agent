using FtpAgent.State;
using Microsoft.Extensions.Logging;

namespace FtpAgent.Deployment;

/// <summary>
/// Stub implementation of IDeploymentClient for dry-run and testing scenarios.
/// Logs all operations without performing actual deployments.
/// </summary>
public class StubDeploymentClient : IDeploymentClient
{
    private readonly ILogger<StubDeploymentClient> _logger;
    private int _deploymentCounter;

    public StubDeploymentClient(ILogger<StubDeploymentClient> logger)
    {
        _logger = logger;
    }

    /// <inheritdoc/>
    public Task<DeploymentResult> TriggerDeploymentAsync(string version, string environment)
    {
        var deploymentId = $"stub-deploy-{Interlocked.Increment(ref _deploymentCounter):D4}";

        _logger.LogInformation(
            "[STUB] Triggering deployment. Version: {Version}, Environment: {Environment}, " +
            "Assigned DeploymentId: {DeploymentId}",
            version, environment, deploymentId);

        return Task.FromResult(new DeploymentResult
        {
            Success = true,
            DeploymentId = deploymentId,
            Status = "Queued"
        });
    }

    /// <inheritdoc/>
    public async Task<DeploymentResult> WaitForDeploymentAsync(
        string deploymentId,
        TimeSpan timeout,
        CancellationToken cancellationToken = default)
    {
        _logger.LogInformation(
            "[STUB] Waiting for deployment {DeploymentId}. Simulating 2-second deployment...",
            deploymentId);

        // Simulate a short deployment wait
        await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);

        _logger.LogInformation("[STUB] Deployment {DeploymentId} completed successfully (simulated)", deploymentId);

        return new DeploymentResult
        {
            Success = true,
            DeploymentId = deploymentId,
            Status = "Success"
        };
    }
}
