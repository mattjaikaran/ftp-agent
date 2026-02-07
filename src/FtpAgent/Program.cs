using FtpAgent.CI;
using FtpAgent.Config;
using FtpAgent.Deployment;
using FtpAgent.Diagnostics;
using FtpAgent.Git;
using FtpAgent.Monitoring;
using FtpAgent.Orchestration;
using FtpAgent.State;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace FtpAgent;

public class Program
{
    public static async Task<int> Main(string[] args)
    {
        var dryRun = args.Contains("--dry-run");

        var builder = Host.CreateApplicationBuilder(args);

        builder.Configuration
            .SetBasePath(Path.Combine(AppContext.BaseDirectory))
            .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
            .AddJsonFile($"appsettings.{builder.Environment.EnvironmentName}.json", optional: true, reloadOnChange: true)
            .AddEnvironmentVariables(prefix: "FTPAGENT_")
            .AddCommandLine(args);

        // Bind configuration sections
        builder.Services.Configure<AgentConfig>(builder.Configuration.GetSection("Agent"));
        builder.Services.Configure<GitHubConfig>(builder.Configuration.GetSection("GitHub"));
        builder.Services.Configure<OctopusDeployConfig>(builder.Configuration.GetSection("OctopusDeploy"));
        builder.Services.Configure<DatadogConfig>(builder.Configuration.GetSection("Datadog"));
        builder.Services.Configure<CopilotConfig>(builder.Configuration.GetSection("Copilot"));

        // Register infrastructure services
        builder.Services.AddSingleton<StateStore>();
        builder.Services.AddSingleton<LegacyConfigParser>();
        builder.Services.AddSingleton<NewConfigWriter>();
        builder.Services.AddSingleton<ConfigTranslator>();
        builder.Services.AddSingleton<GitManager>();
        builder.Services.AddSingleton<GitHubActionsMonitor>();
        builder.Services.AddSingleton<DatadogClient>();
        builder.Services.AddSingleton<DiagnosticEngine>();

        // Register deployment client based on dry-run mode
        if (dryRun)
        {
            builder.Services.AddSingleton<IDeploymentClient, StubDeploymentClient>();
            builder.Services.AddSingleton(new DryRunFlag(true));
        }
        else
        {
            builder.Services.AddSingleton<IDeploymentClient, OctopusDeployClient>();
            builder.Services.AddSingleton(new DryRunFlag(false));
        }

        // Register HttpClient factories for external API calls
        builder.Services.AddHttpClient("Octopus", client =>
        {
            var octopusConfig = builder.Configuration.GetSection("OctopusDeploy").Get<OctopusDeployConfig>();
            if (octopusConfig is not null && !string.IsNullOrEmpty(octopusConfig.ServerUrl))
            {
                client.BaseAddress = new Uri(octopusConfig.ServerUrl);
                client.DefaultRequestHeaders.Add("X-Octopus-ApiKey", octopusConfig.ApiKey);
            }
        });

        builder.Services.AddHttpClient("Datadog", client =>
        {
            var datadogConfig = builder.Configuration.GetSection("Datadog").Get<DatadogConfig>();
            if (datadogConfig is not null && !string.IsNullOrEmpty(datadogConfig.ApiUrl))
            {
                client.BaseAddress = new Uri(datadogConfig.ApiUrl);
                client.DefaultRequestHeaders.Add("DD-API-KEY", datadogConfig.ApiKey);
                client.DefaultRequestHeaders.Add("DD-APPLICATION-KEY", datadogConfig.AppKey);
            }
        });

        // Register the orchestrator
        builder.Services.AddSingleton<BatchOrchestrator>();

        var host = builder.Build();

        var logger = host.Services.GetRequiredService<ILogger<Program>>();
        var orchestrator = host.Services.GetRequiredService<BatchOrchestrator>();

        logger.LogInformation("FTP Agent starting. DryRun={DryRun}, Environment={Environment}",
            dryRun, builder.Environment.EnvironmentName);

        using var cts = new CancellationTokenSource();

        Console.CancelKeyPress += (_, e) =>
        {
            e.Cancel = true;
            logger.LogWarning("Shutdown requested via Ctrl+C");
            cts.Cancel();
        };

        try
        {
            await orchestrator.RunAsync(cts.Token);
            logger.LogInformation("FTP Agent completed successfully");
            return 0;
        }
        catch (OperationCanceledException)
        {
            logger.LogWarning("FTP Agent was cancelled");
            return 1;
        }
        catch (Exception ex)
        {
            logger.LogCritical(ex, "FTP Agent terminated with an unhandled exception");
            return 2;
        }
    }
}

/// <summary>
/// Marker record for dependency injection to indicate dry-run mode.
/// </summary>
public record DryRunFlag(bool Enabled);

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
