# FTP File Ingestion Agent - Architecture & Plan

## Overview

An autonomous DevOps agent built as a **GitHub Copilot agent** (C# / .NET 8) that automates the migration of ~1400 file ingestion configurations from a legacy system to a new Docker-based file ingestion app running in EKS Kubernetes.

The agent operates in a fully autonomous feedback loop:
**Translate config -> Commit & Push -> Build (GitHub Actions) -> Deploy (Octopus Deploy) -> Monitor (Datadog) -> Diagnose & Fix -> Repeat**

### LLM Backend
- **Claude Opus 4.5** via GitHub Copilot CLI agent framework
- Used for: semi-structured config translation, error diagnosis from Datadog logs

### Deployment Target
- Linux VMs (dev environment)
- .NET 8 console app

---

## Problem Statement

There is a Docker container sitting in EKS Kubernetes that downloads files from hundreds of SFTP servers and email attachments in Microsoft Outlook/Exchange. It puts them in S3 and notifies downstream apps over SQS.

~1400 files need to be migrated from a legacy system's configuration to the new app's config format. The legacy config is **semi-structured** (has inconsistencies, may need AI interpretation).

### Current Manual Workflow (what we're automating)
1. Take legacy config for a batch of files
2. Manually translate to new app config format
3. Commit, push to GitHub
4. Wait for GitHub Actions to build Docker image
5. Deploy with Octopus Deploy
6. Check Datadog logs to see if files are downloading
7. If errors: read logs, figure out what's wrong, fix config
8. Repeat steps 3-7 until all files work

### Common Issues Encountered
- PGP decryption configuration
- Finding files by day-of-year in filenames
- SFTP key format mismatches (PuTTY vs OpenSSH format)
- Various SFTP connection/path issues

---

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────┐
│                    BatchOrchestrator                     │
│                                                          │
│  ┌────────────┐   ┌────────────┐   ┌────────────────┐  │
│  │ Load next   │──>│ Translate  │──>│ Commit & Push  │  │
│  │ batch       │   │ configs    │   │ (GitManager)   │  │
│  └────────────┘   └────────────┘   └───────┬────────┘  │
│                                             │            │
│                                             v            │
│  ┌────────────┐   ┌────────────┐   ┌────────────────┐  │
│  │ Diagnose   │<──│ Check      │<──│ Wait for Build │  │
│  │ failures   │   │ Datadog    │   │ & Deploy       │  │
│  └─────┬──────┘   └────────────┘   └────────────────┘  │
│        │                                                 │
│        v                                                 │
│  ┌────────────┐                                          │
│  │ Fix config  │──> (loop back to Commit & Push)         │
│  └────────────┘                                          │
└─────────────────────────────────────────────────────────┘
```

### Components

| Component | Responsibility | Integration |
|---|---|---|
| **BatchOrchestrator** | Main loop. Loads batches, coordinates the full cycle, tracks retries | Internal orchestration |
| **ConfigTranslator** | Parses semi-structured legacy config, maps to new format. Uses Opus 4.5 via Copilot for fuzzy interpretation | Copilot CLI (Opus 4.5) |
| **GitManager** | Clone, branch, commit, push. Wraps `git` CLI via `Process` | git CLI |
| **GitHubActionsMonitor** | Polls workflow runs, waits for build success/failure | GitHub REST API via `gh` CLI |
| **IDeploymentClient** | Triggers and monitors deployment. Interface-based so we can swap implementations | Octopus Deploy (TBD) |
| **DatadogClient** | Queries logs by file name/pattern, returns success/failure status | Datadog Logs API |
| **DiagnosticEngine** | Takes Datadog error logs, sends to Opus 4.5 via Copilot, gets config fix suggestions, applies them | Copilot CLI (Opus 4.5) |
| **StateStore** | Persists which files are done/pending/failed + retry count | SQLite |

---

## Copilot Agent Integration

### Agent Definition (`.github/agents/file-migration-agent.agent.md`)

The agent will be defined as a GitHub Copilot agent with:
- **Tools**: `read`, `edit`, `shell`, `search`
- **Persona**: File migration specialist that understands SFTP config, PGP, key formats
- **Workflows**: Config translation, error diagnosis

### How the C# App Calls Copilot

The C# console app invokes the Copilot CLI agent for AI-powered tasks:
- `gh copilot` CLI for interactive AI reasoning
- Structured prompts for config translation and error diagnosis
- The agent framework handles context/memory across interactions

### LLM Usage Points

1. **Config Translation** (ConfigTranslator)
   - Input: Legacy config blob (semi-structured)
   - Prompt: "Translate this legacy file config to the new app YAML format. Here are 5 examples of correct translations: ..."
   - Output: Structured new config

2. **Error Diagnosis** (DiagnosticEngine)
   - Input: Datadog error logs for a failed file
   - Prompt: "These are the Datadog error logs for file X. The current config is Y. What config change would fix this? Common issues include: PGP, key format, path patterns..."
   - Output: Specific config field changes to apply

---

## Project Structure

```
ftp-agent/
├── .github/
│   ├── agents/
│   │   └── file-migration-agent.agent.md    # Copilot agent definition
│   └── workflows/
│       └── ci.yml                            # CI for this agent app itself
├── src/
│   ├── FtpAgent/                             # Main console app
│   │   ├── FtpAgent.csproj
│   │   ├── Program.cs                        # Entry point, DI setup
│   │   ├── Orchestration/
│   │   │   ├── BatchOrchestrator.cs          # Main autonomous loop
│   │   │   └── AgentConfig.cs                # Batch size, timeouts, retry limits
│   │   ├── Config/
│   │   │   ├── ConfigTranslator.cs           # Legacy -> new config (via Copilot/Opus)
│   │   │   ├── LegacyConfigParser.cs         # Parse semi-structured legacy config
│   │   │   └── NewConfigWriter.cs            # Write new config format
│   │   ├── Git/
│   │   │   └── GitManager.cs                 # Git CLI wrapper (commit, push, branch)
│   │   ├── CI/
│   │   │   └── GitHubActionsMonitor.cs       # Poll GH Actions for build status
│   │   ├── Deployment/
│   │   │   ├── IDeploymentClient.cs          # Interface (swap implementations)
│   │   │   ├── OctopusDeployClient.cs        # Octopus REST API implementation
│   │   │   └── StubDeploymentClient.cs       # Stub for dev/testing
│   │   ├── Monitoring/
│   │   │   └── DatadogClient.cs              # Datadog Logs API queries
│   │   ├── Diagnostics/
│   │   │   └── DiagnosticEngine.cs           # Error diagnosis via Copilot/Opus
│   │   └── State/
│   │       ├── MigrationState.cs             # File migration status model
│   │       └── StateStore.cs                 # SQLite persistence
│   └── FtpAgent.Tests/
│       ├── FtpAgent.Tests.csproj
│       └── ...
├── config/
│   ├── appsettings.json                      # Runtime config (API endpoints, batch size)
│   ├── appsettings.Development.json          # Dev overrides
│   └── legacy-file-list.csv                  # The ~1400 files to migrate
├── prompts/
│   ├── config-translation.md                 # Prompt template for config translation
│   └── error-diagnosis.md                    # Prompt template for error diagnosis
├── ARCHITECTURE.md                           # This file
└── README.md
```

---

## Configuration

### `appsettings.json`

```json
{
  "Agent": {
    "BatchSize": 20,
    "MaxRetriesPerFile": 3,
    "DeployWaitTimeoutMinutes": 15,
    "DatadogCheckDelayMinutes": 5,
    "LogQueryWindowMinutes": 30
  },
  "GitHub": {
    "RepoOwner": "",
    "RepoName": "",
    "TargetBranch": "main",
    "WorkflowFileName": "build.yml"
  },
  "OctopusDeploy": {
    "ServerUrl": "",
    "ApiKey": "",
    "ProjectName": "",
    "EnvironmentName": "Development"
  },
  "Datadog": {
    "ApiKey": "",
    "AppKey": "",
    "Site": "datadoghq.com",
    "SuccessLogPattern": "",
    "FailureLogPattern": "",
    "ServiceName": ""
  },
  "Copilot": {
    "Model": "claude-opus-4-5-20250929",
    "MaxTokens": 4096
  }
}
```

---

## Core Loop (Detailed Pseudo-code)

```csharp
// Program.cs - Entry point
var orchestrator = host.Services.GetRequiredService<BatchOrchestrator>();
await orchestrator.RunAsync(cancellationToken);

// BatchOrchestrator.RunAsync
while (stateStore.HasPendingFiles())
{
    var batch = stateStore.GetNextBatch(config.BatchSize);
    logger.LogInformation("Processing batch of {Count} files", batch.Count);

    // 1. Translate configs (uses Opus 4.5 via Copilot for semi-structured input)
    foreach (var file in batch)
    {
        var newConfig = await configTranslator.TranslateAsync(file.LegacyConfig);
        file.NewConfig = newConfig;
        await configWriter.WriteConfigAsync(file);
        stateStore.MarkInProgress(file);
    }

    // 2. Commit & push
    var message = $"migrate: batch {batch.BatchId} ({batch.Count} files)";
    var commitHash = await gitManager.CommitAndPushAsync(message);

    // 3. Wait for GitHub Actions build
    var buildResult = await ghActionsMonitor.WaitForWorkflowAsync(commitHash, config.DeployTimeout);
    if (!buildResult.Success)
    {
        logger.LogError("Build failed: {Error}", buildResult.Error);
        // Use DiagnosticEngine to understand build failure
        var diagnosis = await diagnosticEngine.DiagnoseBuildFailureAsync(buildResult.Logs);
        // Apply fix and retry...
        continue;
    }

    // 4. Trigger deployment
    var deployId = await deploymentClient.TriggerDeploymentAsync(buildResult.Version, config.Environment);
    var deployResult = await deploymentClient.WaitForDeploymentAsync(deployId, config.DeployTimeout);
    if (!deployResult.Success)
    {
        logger.LogError("Deployment failed: {Error}", deployResult.Error);
        continue;
    }

    // 5. Wait for files to start downloading
    await Task.Delay(TimeSpan.FromMinutes(config.DatadogCheckDelayMinutes));

    // 6. Check Datadog for each file
    foreach (var file in batch)
    {
        var logResult = await datadogClient.QueryLogsAsync(
            file.Identifier,
            TimeSpan.FromMinutes(config.LogQueryWindowMinutes));

        if (logResult.HasSuccessPattern)
        {
            stateStore.MarkSuccess(file);
            logger.LogInformation("File {Name} migrated successfully", file.Name);
        }
        else if (file.RetryCount < config.MaxRetries)
        {
            // 7. Diagnose and fix via Opus 4.5
            var diagnosis = await diagnosticEngine.DiagnoseAsync(file, logResult.Errors);
            await configWriter.ApplyFixAsync(file, diagnosis.ConfigChanges);
            stateStore.IncrementRetry(file);
            logger.LogWarning("File {Name} failed, retry {Count}/{Max}: {Diagnosis}",
                file.Name, file.RetryCount, config.MaxRetries, diagnosis.Summary);
        }
        else
        {
            stateStore.MarkFailed(file);
            logger.LogError("File {Name} exceeded max retries, needs manual intervention", file.Name);
        }
    }
}

// Final report
var report = stateStore.GenerateReport();
logger.LogInformation("Migration complete: {Success} succeeded, {Failed} failed, {Pending} pending",
    report.SuccessCount, report.FailedCount, report.PendingCount);
```

---

## Information Needed From You

Before we can start building, we need the following. Please fill in what you can:

### HIGH PRIORITY (blocks development)

- [ ] **Legacy config sample**: Provide 3-5 examples of the legacy file configuration (the semi-structured format). We need this to build the ConfigTranslator and the translation prompt.

- [ ] **New config sample**: Provide 3-5 examples of what the correctly translated new config looks like. We need this for the prompt examples and validation.

- [ ] **Datadog API credentials**: We need an API key and Application key for the Datadog Logs API.
  - API Key: `_______________`
  - App Key: `_______________`
  - Datadog Site (e.g., datadoghq.com): `_______________`

- [ ] **Datadog log patterns**: What does a successful file download look like in Datadog? What does a failure look like? Provide example log lines if possible.
  - Success pattern: `_______________`
  - Failure pattern: `_______________`
  - Service/source name in Datadog: `_______________`

### MEDIUM PRIORITY (needed before full autonomy)

- [ ] **Octopus Deploy access**: How is deployment triggered today?
  - Octopus Server URL: `_______________`
  - API Key (or how to get one): `_______________`
  - Project name in Octopus: `_______________`
  - Environment name: `_______________`
  - Do you use the Octopus REST API, CLI, or only the UI today?

- [ ] **GitHub repo for the file ingestion app** (not this agent repo): What's the repo URL where config changes get committed?
  - Repo: `_______________`
  - Branch strategy (push to main? feature branches?): `_______________`
  - GitHub Actions workflow file name: `_______________`

- [ ] **GitHub PAT or auth**: Does the Linux VM have `gh` CLI authenticated? Do we need a Personal Access Token?
  - Scopes needed: `repo`, `workflow`, `read:org`

### LOWER PRIORITY (can stub out initially)

- [ ] **Legacy file list**: The CSV/spreadsheet of all ~1400 files. Columns? Format?

- [ ] **Known error patterns**: List of common errors encountered during manual migration (PGP issues, key format, path patterns, etc.) — the more examples the better for the diagnostic prompt.

- [ ] **Structured logging context fields**: From the LogCtx screenshots — what fields does the app log that we should query in Datadog? (e.g., `file_name`, `sftp_host`, `download_status`)

---

## Tech Stack

| Technology | Purpose |
|---|---|
| .NET 8 | Runtime (cross-platform, runs on Linux VMs) |
| C# 12 | Language |
| GitHub Copilot CLI Agent Framework | Agent definition + AI orchestration |
| Claude Opus 4.5 (via Copilot) | LLM for config translation + error diagnosis |
| `gh` CLI | GitHub API interactions (Actions, repos) |
| `git` CLI | Version control operations |
| SQLite (via Microsoft.Data.Sqlite) | Local state persistence |
| Microsoft.Extensions.Hosting | DI, configuration, logging |
| Datadog API (HTTP) | Log queries |
| Octopus Deploy API (HTTP) | Deployment triggers (TBD) |

---

## Getting Started (for the dev VM)

```bash
# 1. Prerequisites
dotnet --version   # Need .NET 8+
gh --version       # Need GitHub CLI
git --version      # Need git

# 2. Clone this repo
git clone git@github.com:mattjaikaran/ftp-agent.git
cd ftp-agent

# 3. Build
dotnet build src/FtpAgent/FtpAgent.csproj

# 4. Configure
cp config/appsettings.json config/appsettings.Development.json
# Edit appsettings.Development.json with your API keys

# 5. Run (dry run mode - no actual commits/deploys)
dotnet run --project src/FtpAgent -- --dry-run

# 6. Run (full autonomous mode)
dotnet run --project src/FtpAgent
```

---

## Next Steps

1. **You** fill in the "Information Needed" section above and send it back
2. **We** build out the C# scaffolding with stubs for all components
3. **We** implement ConfigTranslator first (since it needs legacy config samples)
4. **We** implement GitManager + GitHubActionsMonitor (these are straightforward)
5. **We** implement DatadogClient once we have API keys and patterns
6. **We** implement OctopusDeployClient once we know the API
7. **We** wire up the BatchOrchestrator and test end-to-end in dry-run mode
8. **We** run it for real on a small batch (5 files) to validate
9. **We** scale up to full batches
