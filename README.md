# FTP Agent

[![.NET 8](https://img.shields.io/badge/.NET-8.0-512BD4?logo=dotnet&logoColor=white)](https://dotnet.microsoft.com/download/dotnet/8.0)
[![Claude Opus 4.5](https://img.shields.io/badge/LLM-Claude%20Opus%204.5-orange)](https://docs.github.com/en/copilot)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)]()

**An autonomous DevOps agent that migrates ~1400 file ingestion configurations from a legacy system to a new Docker-based app running in EKS Kubernetes.**

---

## Overview

FTP Agent is an autonomous DevOps agent built as a **GitHub Copilot agent** in C# (.NET 8). It automates the end-to-end migration of approximately 1,400 SFTP and Exchange file ingestion configurations from a legacy system to a new containerized file ingestion application deployed on Amazon EKS.

The agent operates in a fully autonomous feedback loop: it translates legacy configurations into the new format using AI, commits and pushes the changes to GitHub, monitors the GitHub Actions CI build, triggers deployment via Octopus Deploy, monitors Datadog logs to verify files are downloading correctly, and -- when errors occur -- uses Claude Opus 4.5 to diagnose the issue and generate a config fix. This cycle repeats automatically until all files are migrated successfully or flagged for manual intervention.

The AI backbone is **Claude Opus 4.5**, accessed through the GitHub Copilot CLI agent framework. Claude handles two critical tasks that are difficult to automate deterministically: interpreting the semi-structured (and sometimes inconsistent) legacy configuration format, and diagnosing runtime errors from production logs to suggest targeted configuration fixes.

---

## The Problem

A Docker container running in EKS Kubernetes downloads files from hundreds of SFTP servers and Microsoft Outlook/Exchange email attachments, deposits them into S3, and notifies downstream applications over SQS. Approximately **1,400 file configurations** need to be migrated from the legacy system's format to the new application's configuration format.

The legacy configuration is **semi-structured** -- it has inconsistencies, ambiguous fields, and edge cases that require human judgment (or AI interpretation) to resolve correctly.

### The Current Manual Workflow

Today, each batch of file migrations follows this tedious, error-prone cycle:

1. Take a batch of legacy configurations
2. Manually translate each one to the new config format
3. Commit and push to GitHub
4. Wait for GitHub Actions to build the Docker image
5. Deploy via Octopus Deploy
6. Check Datadog logs to verify files are downloading
7. If errors appear: read the logs, diagnose the issue, fix the config
8. Repeat steps 3-7 until every file in the batch works

Multiply this by 1,400 files, and the manual effort becomes untenable. Common issues encountered during migration include PGP decryption configuration errors, date-pattern mismatches in filenames (day-of-year formats), SFTP key format mismatches (PuTTY `.ppk` vs OpenSSH format), and various SFTP connection and path resolution issues.

FTP Agent automates this entire workflow.

---

## How It Works

```
                         FTP Agent - Autonomous Migration Loop
 ============================================================================

   +---------------------+
   |  Load next batch    |   Read pending files from SQLite state store
   |  from state store   |
   +---------+-----------+
             |
             v
   +---------------------+
   |  Translate configs   |   Claude Opus 4.5 interprets semi-structured
   |  (AI-powered)        |   legacy config and generates new format
   +---------+-----------+
             |
             v
   +---------------------+
   |  Commit & Push       |   GitManager writes configs, commits, pushes
   |  to GitHub           |   to the target repository
   +---------+-----------+
             |
             v
   +---------------------+
   |  Wait for CI Build   |   GitHubActionsMonitor polls workflow runs
   |  (GitHub Actions)    |   until build succeeds or fails
   +---------+-----------+
             |
             v
   +---------------------+
   |  Trigger Deployment  |   OctopusDeployClient triggers and monitors
   |  (Octopus Deploy)    |   deployment to the target environment
   +---------+-----------+
             |
             v
   +---------------------+
   |  Monitor Logs        |   DatadogClient queries logs for each file
   |  (Datadog)           |   to detect success or failure patterns
   +---------+-----------+
             |
        +----+----+
        |         |
     Success   Failure
        |         |
        v         v
   +--------+  +---------------------+
   | Mark    |  |  Diagnose error     |   Claude Opus 4.5 analyzes error logs
   | done    |  |  (AI-powered)       |   and suggests config fixes
   +--------+  +---------+-----------+
                          |
                          v
                 +---------------------+
                 |  Apply config fix   |   Write corrected config and loop
                 |  & retry            |   back to Commit & Push
                 +---------------------+
                          |
                          +---------> (back to Commit & Push)

   After max retries exhausted: file is flagged for manual intervention.
   After all files processed: final report is generated.
```

---

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0) | 8.0+ | Build and run the agent |
| [GitHub CLI (`gh`)](https://cli.github.com/) | 2.x+ | GitHub API interactions, Copilot CLI access |
| [Git](https://git-scm.com/) | 2.x+ | Version control operations |
| GitHub Copilot CLI access | -- | AI-powered config translation and error diagnosis |
| Datadog API Key + App Key | -- | Log monitoring via the Datadog Logs API |
| Octopus Deploy access | -- | Deployment triggering and monitoring |

Ensure the GitHub CLI is authenticated (`gh auth login`) and has Copilot access enabled on your account or organization.

---

## Quick Start

```bash
# 1. Verify prerequisites
dotnet --version    # Expect 8.x
gh --version        # Expect 2.x+
git --version       # Expect 2.x+

# 2. Clone the repository
git clone git@github.com:mattjaikaran/ftp-agent.git
cd ftp-agent

# 3. Build the project
dotnet build src/FtpAgent/FtpAgent.csproj

# 4. Set up configuration
cp config/appsettings.json config/appsettings.Development.json
# Edit config/appsettings.Development.json with your API keys and settings
# (see Configuration section below)

# 5. Run in dry-run mode (no actual commits, deploys, or API calls)
dotnet run --project src/FtpAgent -- --dry-run

# 6. Run in full autonomous mode
dotnet run --project src/FtpAgent
```

### Dry-Run Mode

The `--dry-run` flag swaps the Octopus Deploy client for a stub implementation and prevents actual git pushes and deployment triggers. Use this to validate configuration translation logic and the overall orchestration flow without side effects.

### Graceful Shutdown

Press `Ctrl+C` at any time to request a graceful shutdown. The agent will complete the current operation and persist state before exiting.

---

## Configuration

All runtime configuration lives in `config/appsettings.json`. Create a `config/appsettings.Development.json` for local overrides (this file is excluded from publish output). Environment variables prefixed with `FTPAGENT_` will also be read.

```jsonc
{
  // Agent orchestration settings
  "Agent": {
    "BatchSize": 20,                      // Number of files per migration batch
    "MaxRetriesPerFile": 3,               // Max AI-assisted fix attempts per file
    "DeployWaitTimeoutMinutes": 15,       // Max time to wait for deployment
    "DatadogCheckDelayMinutes": 5,        // Wait time before querying logs
    "LogQueryWindowMinutes": 30           // Time window for Datadog log queries
  },

  // Target repository (the file ingestion app, not this agent)
  "GitHub": {
    "Repository": "org/file-ingestion-app",
    "BaseBranch": "main",
    "WorkflowName": "build.yml",
    "TargetRepoPath": "/path/to/local/clone"
  },

  // Octopus Deploy settings
  "OctopusDeploy": {
    "ServerUrl": "https://octopus.example.com",
    "ApiKey": "",                          // Octopus API key
    "ProjectName": "File Ingestion App",
    "EnvironmentName": "Development",
    "SpaceId": "Spaces-1"
  },

  // Datadog log monitoring
  "Datadog": {
    "ApiUrl": "https://api.datadoghq.com",
    "ApiKey": "",                          // Datadog API key
    "AppKey": "",                          // Datadog Application key
    "ServiceName": "file-ingestion-app",
    "Environment": "dev"
  },

  // Copilot / LLM settings
  "Copilot": {
    "CliPath": "gh",                       // Path to GitHub CLI binary
    "Model": "claude-opus-4-5-20250514",   // Claude model used via Copilot
    "TimeoutSeconds": 120,                 // Max time per AI call
    "ConfigTranslationPromptPath": "prompts/config-translation.md",
    "ErrorDiagnosisPromptPath": "prompts/error-diagnosis.md"
  }
}
```

### Environment Variable Overrides

Any configuration value can be overridden via environment variables using the `FTPAGENT_` prefix with double-underscore section separators:

```bash
export FTPAGENT_Datadog__ApiKey="your-api-key"
export FTPAGENT_OctopusDeploy__ApiKey="your-api-key"
```

---

## Project Structure

```
ftp-agent/
├── .github/
│   └── agents/
│       └── file-migration-agent.agent.md  # GitHub Copilot agent definition
├── src/
│   ├── FtpAgent/                          # Main console application
│   │   ├── FtpAgent.csproj               # Project file (.NET 8, SQLite, Hosting)
│   │   ├── Program.cs                    # Entry point, DI container setup
│   │   ├── Orchestration/                # Core autonomous loop
│   │   │   ├── BatchOrchestrator.cs      # Main migration loop coordinator
│   │   │   └── AgentConfig.cs            # Batch size, timeouts, retry limits
│   │   ├── Config/                       # Configuration translation
│   │   │   ├── ConfigTranslator.cs       # Legacy -> new format (via Copilot/Opus)
│   │   │   ├── LegacyConfigParser.cs     # Parse semi-structured legacy configs
│   │   │   └── NewConfigWriter.cs        # Write validated new config format
│   │   ├── Git/                          # Version control operations
│   │   │   └── GitManager.cs             # Git CLI wrapper (commit, push, branch)
│   │   ├── CI/                           # Continuous integration monitoring
│   │   │   └── GitHubActionsMonitor.cs   # Poll GitHub Actions for build status
│   │   ├── Deployment/                   # Deployment management
│   │   │   ├── IDeploymentClient.cs      # Interface (swappable implementations)
│   │   │   ├── OctopusDeployClient.cs    # Octopus Deploy REST API client
│   │   │   └── StubDeploymentClient.cs   # No-op stub for dry-run / testing
│   │   ├── Monitoring/                   # Production log monitoring
│   │   │   └── DatadogClient.cs          # Datadog Logs API query client
│   │   ├── Diagnostics/                  # AI-powered error diagnosis
│   │   │   └── DiagnosticEngine.cs       # Error analysis via Copilot/Opus 4.5
│   │   └── State/                        # Migration state persistence
│   │       ├── MigrationState.cs         # File migration status model
│   │       └── StateStore.cs             # SQLite-backed state persistence
│   └── FtpAgent.Tests/                   # Unit and integration tests
├── config/
│   ├── appsettings.json                  # Default runtime configuration
│   ├── appsettings.Development.json      # Local dev overrides (not committed)
│   └── legacy-file-list.csv             # Source list of ~1400 files to migrate
├── prompts/
│   ├── config-translation.md             # Prompt template for config translation
│   └── error-diagnosis.md               # Prompt template for error diagnosis
├── ARCHITECTURE.md                       # Detailed architecture and design doc
└── README.md                             # This file
```

---

## Components

### Orchestration (`BatchOrchestrator`, `AgentConfig`)

The heart of the agent. `BatchOrchestrator` implements the main autonomous loop: it pulls the next batch of pending files from the state store, coordinates all downstream components, handles retries, and generates a final migration report. `AgentConfig` holds tunable parameters like batch size, timeout durations, and maximum retry counts.

### Config Translation (`ConfigTranslator`, `LegacyConfigParser`, `NewConfigWriter`)

Handles the conversion of legacy file ingestion configurations to the new application's format. `LegacyConfigParser` reads the semi-structured legacy config (which may contain inconsistencies and ambiguous fields). `ConfigTranslator` sends the parsed data to Claude Opus 4.5 via the Copilot CLI with few-shot examples to produce a correct translation. `NewConfigWriter` validates and writes the output in the required format.

### Git (`GitManager`)

Wraps the `git` CLI via `System.Diagnostics.Process`. Handles staging config files, committing with descriptive batch messages, and pushing to the target repository's branch. Operates on a local clone of the file ingestion app repository (not this agent's repo).

### CI Monitoring (`GitHubActionsMonitor`)

Polls GitHub Actions workflow runs via the `gh` CLI to track build status after each push. Waits for the Docker image build to succeed or fail, with configurable timeout. On build failure, surfaces the build logs for diagnosis.

### Deployment (`IDeploymentClient`, `OctopusDeployClient`, `StubDeploymentClient`)

Interface-based design allows swapping deployment backends. `OctopusDeployClient` triggers deployments and monitors their status via the Octopus Deploy REST API. `StubDeploymentClient` is a no-op implementation used in dry-run mode and testing -- it simulates successful deployments without making any API calls.

### Monitoring (`DatadogClient`)

Queries the Datadog Logs API to determine whether migrated files are being downloaded successfully. Searches for configurable success and failure log patterns within a time window after deployment. Returns structured results indicating which files succeeded and which produced errors.

### Diagnostics (`DiagnosticEngine`)

The AI-powered error resolution component. When Datadog logs indicate a file is failing, the `DiagnosticEngine` sends the error logs along with the current configuration to Claude Opus 4.5. The LLM analyzes the error context (drawing on knowledge of common issues like PGP misconfiguration, key format mismatches, and path pattern errors) and returns specific configuration field changes to apply.

### State (`MigrationState`, `StateStore`)

SQLite-backed persistence layer that tracks every file's migration status: pending, in-progress, success, or failed. Records retry counts and diagnostic history. Enables the agent to resume from where it left off after a restart, and generates summary reports on completion.

---

## Copilot Agent Integration

### Agent Definition

The file `.github/agents/file-migration-agent.agent.md` defines the agent's persona and capabilities for the GitHub Copilot CLI framework:

- **Tools**: `read`, `edit`, `shell`, `search` -- standard Copilot agent tools for file manipulation and command execution
- **Persona**: A file migration specialist with deep knowledge of SFTP configuration, PGP encryption, SSH key formats, and the specific legacy/new config schemas
- **Workflows**: Config translation (legacy to new format) and error diagnosis (Datadog logs to config fixes)

### How the C# App Uses Copilot

The C# console app invokes Claude Opus 4.5 through the `gh copilot` CLI:

1. **Config Translation** -- The `ConfigTranslator` constructs a prompt from the template in `prompts/config-translation.md`, injects the legacy config blob and few-shot examples of correct translations, and sends it to Claude via the Copilot CLI. Claude returns a structured new-format configuration.

2. **Error Diagnosis** -- The `DiagnosticEngine` constructs a prompt from `prompts/error-diagnosis.md`, injects the Datadog error logs and current config, and asks Claude to identify the root cause and suggest specific field-level fixes. Claude returns actionable configuration changes.

### Invoking the Agent

```bash
# Via Copilot CLI (interactive mode)
gh copilot agent file-migration-agent

# Via the C# application (programmatic)
dotnet run --project src/FtpAgent
```

---

## Development

### Building

```bash
# Build the main project
dotnet build src/FtpAgent/FtpAgent.csproj

# Build the entire solution (includes tests)
dotnet build
```

### Running Tests

```bash
# Run all tests
dotnet test src/FtpAgent.Tests/

# Run with verbose output
dotnet test src/FtpAgent.Tests/ --verbosity normal
```

### Project Dependencies

| Package | Version | Purpose |
|---|---|---|
| `Microsoft.Extensions.Hosting` | 8.0.1 | Dependency injection, configuration, logging |
| `Microsoft.Extensions.Http` | 8.0.1 | `HttpClientFactory` for Datadog and Octopus API calls |
| `Microsoft.Data.Sqlite` | 8.0.11 | SQLite state persistence |

### Code Organization Conventions

- Each component lives in its own namespace under `FtpAgent` (e.g., `FtpAgent.Git`, `FtpAgent.Monitoring`)
- External service clients are registered via `IHttpClientFactory` with named clients
- The `IDeploymentClient` interface demonstrates the pattern for swappable implementations
- Configuration classes are bound via `IOptions<T>` from `appsettings.json` sections
- All external process calls (git, gh) go through `System.Diagnostics.Process`

### Contributing

1. Create a feature branch from `main`
2. Make your changes with clear, descriptive commits
3. Ensure all tests pass (`dotnet test`)
4. Open a pull request with a description of what changed and why

---

## Roadmap

- [ ] **Parallel batch processing** -- Process multiple batches concurrently where CI/CD pipeline allows
- [ ] **Web dashboard** -- Real-time migration progress dashboard showing file statuses, retry counts, and error trends
- [ ] **Slack/Teams notifications** -- Alert on batch completion, failures exceeding retry limits, or agent errors
- [ ] **Prompt tuning pipeline** -- Automated evaluation of config translation accuracy with a labeled test set to iterate on prompts
- [ ] **Rollback automation** -- Automatically revert config changes if a deployment causes regressions in previously-working files
- [ ] **Multi-environment support** -- Extend the agent to promote configs through dev, staging, and production environments sequentially
- [ ] **Metrics and observability** -- Emit agent-level metrics (translation accuracy, retry rates, cycle time) to Datadog
- [ ] **Config validation layer** -- Schema-based pre-validation of generated configs before committing, to catch errors before the CI/CD cycle
- [ ] **Resume intelligence** -- Smarter batch prioritization on restart (e.g., retry recently-failed files first, deprioritize files with persistent errors)

---

## Tech Stack

| Technology | Purpose |
|---|---|
| .NET 8 / C# 12 | Runtime and language |
| GitHub Copilot CLI Agent Framework | Agent definition and AI orchestration |
| Claude Opus 4.5 (via Copilot) | LLM for config translation and error diagnosis |
| GitHub CLI (`gh`) | GitHub API interactions (Actions, repos, Copilot) |
| Git CLI | Version control operations |
| SQLite | Local state persistence |
| Microsoft.Extensions.Hosting | Dependency injection, configuration, structured logging |
| Datadog Logs API | Production log monitoring |
| Octopus Deploy REST API | Deployment triggering and monitoring |
| Amazon EKS | Target Kubernetes environment |
| Docker | Container runtime for the file ingestion app |

---

## Documentation

| Document | Description |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Detailed architecture, component design, pseudo-code, and data flow |
| SETUP.md | Step-by-step environment setup and credential configuration |
| TROUBLESHOOTING.md | Common issues, error messages, and resolution steps |
| CONTRIBUTING.md | Contribution guidelines, code standards, and PR process |
| WALKTHROUGH.md | End-to-end walkthrough of a migration batch with annotated logs |

---

