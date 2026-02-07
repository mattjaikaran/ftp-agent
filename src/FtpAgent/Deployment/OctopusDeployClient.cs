using FtpAgent;
using FtpAgent.Orchestration;
using FtpAgent.State;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace FtpAgent.Deployment;

/// <summary>
/// Implements deployment operations against the Octopus Deploy REST API.
/// Handles release creation, deployment triggering, and status polling.
/// </summary>
public class OctopusDeployClient : IDeploymentClient
{
    private readonly ILogger<OctopusDeployClient> _logger;
    private readonly HttpClient _httpClient;
    private readonly OctopusDeployConfig _config;
    private readonly AgentConfig _agentConfig;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public OctopusDeployClient(
        ILogger<OctopusDeployClient> logger,
        IHttpClientFactory httpClientFactory,
        IOptions<OctopusDeployConfig> config,
        IOptions<AgentConfig> agentConfig)
    {
        _logger = logger;
        _httpClient = httpClientFactory.CreateClient("Octopus");
        _config = config.Value;
        _agentConfig = agentConfig.Value;
    }

    /// <inheritdoc/>
    public async Task<DeploymentResult> TriggerDeploymentAsync(string version, string environment)
    {
        _logger.LogInformation("Triggering Octopus deployment. Version: {Version}, Environment: {Environment}",
            version, environment);

        try
        {
            // Step 1: Find or create a release for this version
            var releaseId = await CreateReleaseAsync(version);
            _logger.LogInformation("Release created/found: {ReleaseId}", releaseId);

            // Step 2: Look up the environment ID
            var environmentId = await GetEnvironmentIdAsync(environment);
            _logger.LogInformation("Environment resolved: {EnvironmentId}", environmentId);

            // Step 3: Create a deployment
            var deploymentRequest = new
            {
                ReleaseId = releaseId,
                EnvironmentId = environmentId,
                Comments = $"Automated deployment by FTP Agent for version {version}"
            };

            var response = await _httpClient.PostAsJsonAsync(
                $"/api/{_config.SpaceId}/deployments",
                deploymentRequest,
                JsonOptions);

            response.EnsureSuccessStatusCode();

            var responseContent = await response.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(responseContent);
            var deploymentId = doc.RootElement.GetProperty("Id").GetString()
                ?? throw new InvalidOperationException("Deployment response missing Id");

            _logger.LogInformation("Deployment created: {DeploymentId}", deploymentId);

            return new DeploymentResult
            {
                Success = true,
                DeploymentId = deploymentId,
                Status = "Queued"
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to trigger deployment for version {Version}", version);
            return new DeploymentResult
            {
                Success = false,
                ErrorMessage = $"Failed to trigger deployment: {ex.Message}"
            };
        }
    }

    /// <inheritdoc/>
    public async Task<DeploymentResult> WaitForDeploymentAsync(string deploymentId, TimeSpan timeout)
    {
        _logger.LogInformation("Waiting for deployment {DeploymentId} (timeout: {Timeout})", deploymentId, timeout);

        var deadline = DateTime.UtcNow + timeout;
        var pollInterval = TimeSpan.FromSeconds(_agentConfig.PollIntervalSeconds);

        while (DateTime.UtcNow < deadline)
        {
            try
            {
                var taskId = await GetDeploymentTaskIdAsync(deploymentId);

                if (taskId is not null)
                {
                    var (state, isComplete, errorMessage) = await GetTaskStatusAsync(taskId);

                    _logger.LogDebug("Deployment {DeploymentId} task state: {State}", deploymentId, state);

                    if (isComplete)
                    {
                        var success = state == "Success";

                        if (success)
                        {
                            _logger.LogInformation("Deployment {DeploymentId} succeeded", deploymentId);
                        }
                        else
                        {
                            _logger.LogWarning("Deployment {DeploymentId} finished with state: {State}. Error: {Error}",
                                deploymentId, state, errorMessage);
                        }

                        return new DeploymentResult
                        {
                            Success = success,
                            DeploymentId = deploymentId,
                            Status = state,
                            ErrorMessage = errorMessage ?? string.Empty
                        };
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Error polling deployment status for {DeploymentId}", deploymentId);
            }

            await Task.Delay(pollInterval);
        }

        _logger.LogError("Deployment {DeploymentId} timed out after {Timeout}", deploymentId, timeout);
        return new DeploymentResult
        {
            Success = false,
            DeploymentId = deploymentId,
            Status = "TimedOut",
            ErrorMessage = $"Deployment did not complete within {timeout}"
        };
    }

    /// <summary>
    /// Creates a release in Octopus Deploy for the given version.
    /// </summary>
    private async Task<string> CreateReleaseAsync(string version)
    {
        // TODO: Resolve the actual project ID from _config.ProjectName via the Octopus API
        var projectId = await GetProjectIdAsync();

        var releaseRequest = new
        {
            ProjectId = projectId,
            Version = version,
            ReleaseNotes = $"Automated release created by FTP Agent migration"
        };

        var response = await _httpClient.PostAsJsonAsync(
            $"/api/{_config.SpaceId}/releases",
            releaseRequest,
            JsonOptions);

        response.EnsureSuccessStatusCode();

        var content = await response.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(content);
        return doc.RootElement.GetProperty("Id").GetString()
            ?? throw new InvalidOperationException("Release response missing Id");
    }

    /// <summary>
    /// Resolves the project ID from the configured project name.
    /// </summary>
    private async Task<string> GetProjectIdAsync()
    {
        // TODO: Cache this value after first lookup
        var response = await _httpClient.GetAsync(
            $"/api/{_config.SpaceId}/projects?name={Uri.EscapeDataString(_config.ProjectName)}");

        response.EnsureSuccessStatusCode();

        var content = await response.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(content);
        var items = doc.RootElement.GetProperty("Items");

        if (items.GetArrayLength() == 0)
        {
            throw new InvalidOperationException($"Project not found in Octopus: {_config.ProjectName}");
        }

        return items[0].GetProperty("Id").GetString()
            ?? throw new InvalidOperationException("Project response missing Id");
    }

    /// <summary>
    /// Resolves an environment ID from the environment name.
    /// </summary>
    private async Task<string> GetEnvironmentIdAsync(string environmentName)
    {
        // TODO: Cache this value after first lookup
        var response = await _httpClient.GetAsync(
            $"/api/{_config.SpaceId}/environments?name={Uri.EscapeDataString(environmentName)}");

        response.EnsureSuccessStatusCode();

        var content = await response.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(content);
        var items = doc.RootElement.GetProperty("Items");

        if (items.GetArrayLength() == 0)
        {
            throw new InvalidOperationException($"Environment not found in Octopus: {environmentName}");
        }

        return items[0].GetProperty("Id").GetString()
            ?? throw new InvalidOperationException("Environment response missing Id");
    }

    /// <summary>
    /// Gets the server task ID associated with a deployment.
    /// </summary>
    private async Task<string?> GetDeploymentTaskIdAsync(string deploymentId)
    {
        var response = await _httpClient.GetAsync(
            $"/api/{_config.SpaceId}/deployments/{deploymentId}");

        response.EnsureSuccessStatusCode();

        var content = await response.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(content);

        if (doc.RootElement.TryGetProperty("TaskId", out var taskIdProp))
        {
            return taskIdProp.GetString();
        }

        return null;
    }

    /// <summary>
    /// Gets the status of a server task.
    /// </summary>
    private async Task<(string state, bool isComplete, string? errorMessage)> GetTaskStatusAsync(string taskId)
    {
        var response = await _httpClient.GetAsync($"/api/tasks/{taskId}");
        response.EnsureSuccessStatusCode();

        var content = await response.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(content);
        var root = doc.RootElement;

        var state = root.GetProperty("State").GetString() ?? "Unknown";
        var isCompleted = root.TryGetProperty("IsCompleted", out var completedProp) && completedProp.GetBoolean();

        string? errorMessage = null;
        if (root.TryGetProperty("ErrorMessage", out var errorProp) && errorProp.ValueKind != JsonValueKind.Null)
        {
            errorMessage = errorProp.GetString();
        }

        return (state, isCompleted, errorMessage);
    }
}
