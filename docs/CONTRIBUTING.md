# Contributing to FTP Agent

Thank you for your interest in contributing to the FTP Agent project. This document covers everything you need to get started: environment setup, coding standards, branch conventions, testing, and how to extend the agent with new components.

---

## Table of Contents

- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [Branch Naming Conventions](#branch-naming-conventions)
- [Running the Application](#running-the-application)
- [Running Tests](#running-tests)
- [Code Style and Conventions](#code-style-and-conventions)
- [Pull Request Process](#pull-request-process)
- [Adding a New Integration or Component](#adding-a-new-integration-or-component)
- [Modifying Prompt Templates](#modifying-prompt-templates)
- [Working with the State Store](#working-with-the-state-store)
- [Debugging Tips](#debugging-tips)

---

## Development Environment Setup

### Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| .NET SDK | 8.0+ | Build and run the C# application |
| Git | 2.30+ | Version control |
| GitHub CLI (`gh`) | 2.0+ | GitHub Actions integration and Copilot CLI |
| SQLite | 3.x | State persistence (included via NuGet, no install needed) |

### Clone and Build

```bash
# Clone the repository
git clone git@github.com:mattjaikaran/ftp-agent.git
cd ftp-agent

# Restore dependencies and build
dotnet build src/FtpAgent/FtpAgent.csproj

# Build the test project
dotnet build src/FtpAgent.Tests/FtpAgent.Tests.csproj
```

### Configuration

Copy the default configuration and fill in your development values:

```bash
cp config/appsettings.json config/appsettings.Development.json
```

Edit `config/appsettings.Development.json` with your API keys and paths. **Never commit `appsettings.Development.json` to the repository** -- it is listed in `.gitignore`.

For local development, you typically only need:

```json
{
  "Agent": {
    "BatchSize": 2,
    "MaxRetriesPerFile": 1,
    "LegacyConfigSourcePath": "config/legacy-file-list.csv",
    "StateDatabasePath": "dev-state.db"
  },
  "Copilot": {
    "Model": "claude-opus-4-5-20250514",
    "ConfigTranslationPromptPath": "prompts/config-translation.md",
    "ErrorDiagnosisPromptPath": "prompts/error-diagnosis.md"
  }
}
```

### Authenticate the GitHub CLI

The agent uses `gh` for GitHub Actions monitoring and Copilot CLI access:

```bash
gh auth login
gh auth status   # Verify authentication

# Verify Copilot access
gh copilot --help
```

---

## Project Structure

```
ftp-agent/
├── src/
│   ├── FtpAgent/                        # Main console application
│   │   ├── Program.cs                   # Entry point, DI container setup
│   │   ├── Orchestration/
│   │   │   ├── BatchOrchestrator.cs     # Main autonomous loop
│   │   │   └── AgentConfig.cs           # Agent configuration POCO
│   │   ├── Config/
│   │   │   ├── ConfigTranslator.cs      # LLM-powered config translation
│   │   │   ├── LegacyConfigParser.cs    # Parse semi-structured legacy configs
│   │   │   └── NewConfigWriter.cs       # Write translated YAML configs
│   │   ├── Git/
│   │   │   └── GitManager.cs            # Git CLI wrapper
│   │   ├── CI/
│   │   │   └── GitHubActionsMonitor.cs  # Poll GitHub Actions workflow runs
│   │   ├── Deployment/
│   │   │   ├── IDeploymentClient.cs     # Deployment abstraction interface
│   │   │   ├── OctopusDeployClient.cs   # Octopus Deploy implementation
│   │   │   └── StubDeploymentClient.cs  # Stub for dry-run and testing
│   │   ├── Monitoring/
│   │   │   └── DatadogClient.cs         # Datadog Logs API queries
│   │   ├── Diagnostics/
│   │   │   └── DiagnosticEngine.cs      # LLM-powered error diagnosis
│   │   └── State/
│   │       ├── MigrationState.cs        # Data models (FileEntry, etc.)
│   │       └── StateStore.cs            # SQLite persistence layer
│   └── FtpAgent.Tests/                  # Unit and integration tests
│       └── FtpAgent.Tests.csproj
├── config/
│   ├── appsettings.json                 # Default configuration
│   └── legacy-file-list.csv             # Source file list
├── prompts/
│   ├── config-translation.md            # Prompt template for translation
│   └── error-diagnosis.md              # Prompt template for diagnosis
├── docs/
│   ├── WALKTHROUGH.md                   # End-to-end walkthrough
│   ├── CONTRIBUTING.md                  # This file
│   └── TROUBLESHOOTING.md              # Troubleshooting guide
└── ARCHITECTURE.md                      # Architecture and design document
```

---

## Branch Naming Conventions

Use the following prefixes for branch names:

| Prefix | Purpose | Example |
|---|---|---|
| `feature/` | New functionality or capability | `feature/add-exchange-protocol` |
| `fix/` | Bug fixes | `fix/datadog-timeout-handling` |
| `docs/` | Documentation changes only | `docs/update-prompt-examples` |
| `refactor/` | Code restructuring without behavior change | `refactor/extract-retry-logic` |
| `test/` | Adding or updating tests | `test/diagnostic-engine-unit-tests` |

Branch names should be lowercase, use hyphens to separate words, and be descriptive but concise.

```bash
# Create a feature branch
git checkout -b feature/add-ftp-passive-mode

# Create a fix branch
git checkout -b fix/octopus-api-auth-header
```

---

## Running the Application

### Dry-Run Mode (Recommended for Development)

```bash
dotnet run --project src/FtpAgent/FtpAgent.csproj -- --dry-run
```

This uses the `StubDeploymentClient` and does not push to remote repositories or trigger real deployments. Config translation still calls Copilot, so you can validate prompt quality.

### Full Mode

```bash
dotnet run --project src/FtpAgent/FtpAgent.csproj
```

Only run full mode when you have all external integrations configured and you intend to make real changes.

### Environment-Specific Configuration

Set the environment name to load the corresponding `appsettings.{Environment}.json`:

```bash
DOTNET_ENVIRONMENT=Development dotnet run --project src/FtpAgent/FtpAgent.csproj -- --dry-run
```

### Environment Variable Overrides

Any configuration value can be overridden via environment variables with the `FTPAGENT_` prefix. Use double underscores for nested keys:

```bash
export FTPAGENT_Agent__BatchSize=2
export FTPAGENT_Agent__MaxRetriesPerFile=1
```

---

## Running Tests

### Run All Tests

```bash
dotnet test src/FtpAgent.Tests/FtpAgent.Tests.csproj
```

### Run Tests with Verbose Output

```bash
dotnet test src/FtpAgent.Tests/FtpAgent.Tests.csproj --verbosity normal
```

### Run a Specific Test Class

```bash
dotnet test src/FtpAgent.Tests/FtpAgent.Tests.csproj --filter "FullyQualifiedName~ConfigTranslatorTests"
```

### Run a Specific Test Method

```bash
dotnet test src/FtpAgent.Tests/FtpAgent.Tests.csproj --filter "FullyQualifiedName~ConfigTranslatorTests.TranslateAsync_WithSftpConfig_ReturnsValidYaml"
```

### Test Conventions

- Test classes follow the pattern `{ClassName}Tests.cs`
- Test methods follow the pattern `{MethodName}_{Scenario}_{ExpectedResult}`
- Use `Moq` or similar for mocking external dependencies
- Tests should not require network access or external services
- Use the `StubDeploymentClient` pattern for integration testing

---

## Code Style and Conventions

### General Rules

- Follow the existing patterns in the codebase. When unsure, look at how similar code is structured in neighboring files.
- Use C# 12 features where they improve readability (file-scoped namespaces, raw string literals, primary constructors).
- Keep methods focused. If a method exceeds ~40 lines, consider extracting a helper.
- Prefer `async/await` throughout. Never use `.Result` or `.Wait()` on tasks.

### Logging

Use `ILogger<T>` everywhere. Inject it via the constructor. Use structured logging with named parameters:

```csharp
// Good
_logger.LogInformation("Processing file {FileName} (attempt {RetryCount}/{MaxRetries})",
    file.Name, file.RetryCount, config.MaxRetriesPerFile);

// Bad - string interpolation defeats structured logging
_logger.LogInformation($"Processing file {file.Name} (attempt {file.RetryCount})");
```

Use appropriate log levels:

| Level | When to Use |
|---|---|
| `LogDebug` | Verbose details useful only during active debugging |
| `LogInformation` | Normal operational events (batch started, file processed, etc.) |
| `LogWarning` | Recoverable problems (retry queued, non-critical timeout) |
| `LogError` | Failures that affect a specific file or operation |
| `LogCritical` | Unrecoverable failures that terminate the agent |

### Dependency Injection

All external dependencies should be injected via constructor injection. Register services in `Program.cs`.

```csharp
public class MyComponent
{
    private readonly ILogger<MyComponent> _logger;
    private readonly StateStore _stateStore;

    public MyComponent(ILogger<MyComponent> logger, StateStore stateStore)
    {
        _logger = logger;
        _stateStore = stateStore;
    }
}
```

### Interfaces for External Dependencies

Any component that talks to an external system (API, CLI, file system) should implement an interface. This enables testing with stubs and future replacement. See `IDeploymentClient` as the canonical example:

```csharp
public interface IDeploymentClient
{
    Task<DeploymentResult> TriggerDeploymentAsync(string version, string environment, CancellationToken ct);
    Task<DeploymentResult> WaitForDeploymentAsync(string deploymentId, TimeSpan timeout, CancellationToken ct);
}
```

### Configuration

Use the Options pattern. Configuration classes are POCOs bound from `appsettings.json` sections:

```csharp
// In your component
public class MyComponent
{
    private readonly MyConfig _config;

    public MyComponent(IOptions<MyConfig> config)
    {
        _config = config.Value;
    }
}

// In Program.cs
builder.Services.Configure<MyConfig>(builder.Configuration.GetSection("MySection"));
```

### Error Handling

- Use exceptions for truly exceptional cases (network failures, corrupted state).
- Use result objects (like `BuildResult`, `DeploymentResult`, `DiagnosticResult`) for expected outcomes that include failure states.
- Always catch `OperationCanceledException` in long-running loops to support graceful shutdown via `Ctrl+C`.
- Never swallow exceptions silently. At minimum, log them.

### Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Classes | PascalCase | `ConfigTranslator` |
| Interfaces | `I` prefix + PascalCase | `IDeploymentClient` |
| Methods | PascalCase | `TranslateAsync` |
| Async methods | `Async` suffix | `CommitAndPushAsync` |
| Private fields | `_camelCase` | `_stateStore` |
| Parameters | camelCase | `batchSize` |
| Constants | PascalCase | `MaxRetryCount` |
| Config classes | `{Section}Config` | `AgentConfig`, `DatadogConfig` |

---

## Pull Request Process

### Before Opening a PR

1. **Ensure all tests pass locally:**
   ```bash
   dotnet test src/FtpAgent.Tests/FtpAgent.Tests.csproj
   ```

2. **Build without warnings:**
   ```bash
   dotnet build src/FtpAgent/FtpAgent.csproj --warnaserrors
   ```

3. **Test in dry-run mode** if your change affects the orchestration loop:
   ```bash
   dotnet run --project src/FtpAgent/FtpAgent.csproj -- --dry-run
   ```

4. **Keep commits atomic and descriptive.** Each commit should represent a single logical change.

### PR Guidelines

- **Title**: Short, imperative mood (e.g., "Add FTP passive mode support", "Fix Datadog query timeout")
- **Description**: Explain what changed and why. Include any relevant context about the migration process.
- **Size**: Keep PRs focused. If a change touches more than 3 components, consider splitting it.
- **Tests**: Include tests for any new logic. Modify existing tests if behavior changed.
- **Breaking changes**: Call out in the PR description if your change affects configuration format, CLI arguments, or external API contracts.

### Review Checklist

Reviewers will look for:

- [ ] Tests pass and cover new/changed logic
- [ ] Logging is appropriate (not too verbose, not too quiet)
- [ ] External dependencies are behind interfaces
- [ ] Configuration values are not hardcoded
- [ ] Error handling is present for failure paths
- [ ] No secrets or credentials in the code
- [ ] Prompt template changes are justified with examples

---

## Adding a New Integration or Component

If you need to add a new external integration (for example, a Slack notifier, a different deployment platform, or a new monitoring tool), follow this pattern:

### 1. Define the Interface

Create an interface in the appropriate directory:

```csharp
// src/FtpAgent/Notifications/INotificationClient.cs
namespace FtpAgent.Notifications;

public interface INotificationClient
{
    Task SendBatchResultAsync(BatchResult result, CancellationToken ct);
    Task SendMigrationReportAsync(MigrationReport report, CancellationToken ct);
}
```

### 2. Create the Implementation

```csharp
// src/FtpAgent/Notifications/SlackNotificationClient.cs
namespace FtpAgent.Notifications;

public class SlackNotificationClient : INotificationClient
{
    private readonly ILogger<SlackNotificationClient> _logger;
    private readonly HttpClient _httpClient;
    private readonly SlackConfig _config;

    public SlackNotificationClient(
        ILogger<SlackNotificationClient> logger,
        IHttpClientFactory httpClientFactory,
        IOptions<SlackConfig> config)
    {
        _logger = logger;
        _httpClient = httpClientFactory.CreateClient("Slack");
        _config = config.Value;
    }

    public async Task SendBatchResultAsync(BatchResult result, CancellationToken ct)
    {
        _logger.LogInformation("Sending batch {BatchNumber} result to Slack", result.BatchNumber);
        // Implementation here
    }

    public async Task SendMigrationReportAsync(MigrationReport report, CancellationToken ct)
    {
        _logger.LogInformation("Sending migration report to Slack");
        // Implementation here
    }
}
```

### 3. Create a Stub for Testing

```csharp
// src/FtpAgent/Notifications/StubNotificationClient.cs
namespace FtpAgent.Notifications;

public class StubNotificationClient : INotificationClient
{
    private readonly ILogger<StubNotificationClient> _logger;

    public StubNotificationClient(ILogger<StubNotificationClient> logger)
    {
        _logger = logger;
    }

    public Task SendBatchResultAsync(BatchResult result, CancellationToken ct)
    {
        _logger.LogDebug("[STUB] Would send batch result to Slack");
        return Task.CompletedTask;
    }

    public Task SendMigrationReportAsync(MigrationReport report, CancellationToken ct)
    {
        _logger.LogDebug("[STUB] Would send migration report to Slack");
        return Task.CompletedTask;
    }
}
```

### 4. Add Configuration

Add a config class and a section to `appsettings.json`:

```csharp
// In Program.cs or a separate file
public class SlackConfig
{
    public string WebhookUrl { get; set; } = string.Empty;
    public string Channel { get; set; } = string.Empty;
}
```

```json
// In appsettings.json
{
  "Slack": {
    "WebhookUrl": "",
    "Channel": "#file-migration"
  }
}
```

### 5. Register in DI Container

```csharp
// In Program.cs
builder.Services.Configure<SlackConfig>(builder.Configuration.GetSection("Slack"));

if (dryRun)
{
    builder.Services.AddSingleton<INotificationClient, StubNotificationClient>();
}
else
{
    builder.Services.AddSingleton<INotificationClient, SlackNotificationClient>();
}
```

### 6. Inject into the Orchestrator

```csharp
// In BatchOrchestrator.cs
public class BatchOrchestrator
{
    private readonly INotificationClient _notifications;

    public BatchOrchestrator(/* existing deps */, INotificationClient notifications)
    {
        _notifications = notifications;
    }
}
```

### 7. Write Tests

```csharp
// src/FtpAgent.Tests/Notifications/SlackNotificationClientTests.cs
public class SlackNotificationClientTests
{
    [Fact]
    public async Task SendBatchResultAsync_WithSuccessfulBatch_SendsFormattedMessage()
    {
        // Arrange, Act, Assert
    }
}
```

---

## Modifying Prompt Templates

The prompt templates in `prompts/` are critical to the agent's accuracy. Changes to these files directly affect config translation quality and error diagnosis accuracy.

### Prompt File Locations

| File | Purpose | Used By |
|---|---|---|
| `prompts/config-translation.md` | Translates legacy config to new YAML | `ConfigTranslator` |
| `prompts/error-diagnosis.md` | Diagnoses failures from Datadog logs | `DiagnosticEngine` |

### Guidelines for Prompt Changes

1. **Test before committing.** Run the agent in dry-run mode with a few known files to verify the prompt produces correct output.

2. **Add examples, do not remove them.** The prompt templates use few-shot examples to guide the LLM. If you encounter a new config pattern that the LLM gets wrong, add a correct example to the prompt rather than rewriting instructions.

3. **Be specific in instructions.** Vague instructions like "handle edge cases" do not help. Instead, specify: "If the legacy config contains a `DayOfYear` field, convert it to a cron expression using the `Day of Year` cron syntax."

4. **Include the failure mode.** When adding a new known error pattern to `error-diagnosis.md`, include both the error log text that will appear and the correct fix. For example:

   ```markdown
   ## Known Issue: Exchange OAuth Token Expired
   Error log pattern: "Exchange authentication failed: token expired"
   Fix: This is not a config issue. The OAuth refresh token needs to be
   regenerated manually. Mark as non-recoverable.
   ```

5. **Version your prompts.** When making significant prompt changes, note the change in your PR description and include before/after examples of the LLM output.

### Template Variables

Prompt templates use `${VARIABLE_NAME}` placeholders that are replaced at runtime:

| Variable | Available In | Value |
|---|---|---|
| `${LEGACY_CONFIG}` | config-translation.md | Raw legacy config text |
| `${CURRENT_CONFIG}` | error-diagnosis.md | Current YAML config |
| `${ERROR_LOGS}` | error-diagnosis.md | Datadog error log entries |
| `${FILE_NAME}` | error-diagnosis.md | Human-readable file name |
| `${PROTOCOL}` | error-diagnosis.md | SFTP, FTP, Exchange, etc. |
| `${RETRY_COUNT}` | error-diagnosis.md | Current retry attempt number |
| `${MAX_RETRIES}` | error-diagnosis.md | Max retries configured |

---

## Working with the State Store

The `StateStore` uses SQLite to persist migration state across runs. If you need to inspect or manipulate state during development:

### Inspect the Database

```bash
sqlite3 dev-state.db

# Show all tables
.tables

# Show schema
.schema file_entries

# Count by status
SELECT Status, COUNT(*) FROM file_entries GROUP BY Status;

# Find files stuck in InProgress
SELECT Id, Name, UpdatedAt FROM file_entries WHERE Status = 1;
```

### Manually Reset a File

```bash
sqlite3 dev-state.db "UPDATE file_entries SET Status = 0, RetryCount = 0, LastError = '' WHERE Id = 'file-0321';"
```

### Reset All State

```bash
rm dev-state.db
# The agent will recreate it on next run
```

---

## Debugging Tips

### Verbose Logging

Set the log level to `Debug` in your development config:

```json
{
  "Logging": {
    "LogLevel": {
      "Default": "Debug",
      "FtpAgent": "Debug"
    }
  }
}
```

### Inspect Copilot Prompts

To see the exact prompts being sent to Copilot, set `Debug` logging for the `ConfigTranslator` and `DiagnosticEngine` classes. The rendered prompt is logged at `Debug` level before being sent.

### Small Batch Sizes

Use `BatchSize: 1` or `BatchSize: 2` during development to iterate quickly without waiting for large batches to process.

### Skip Specific Steps

During development, you may want to isolate specific components. Use the `--dry-run` flag and set environment variables to control behavior:

```bash
# Only test config translation (skip deploy/monitor)
dotnet run --project src/FtpAgent/FtpAgent.csproj -- --dry-run
```

---

## Questions?

If you have questions not covered here, check:

- `ARCHITECTURE.md` in the project root for system design decisions
- `docs/WALKTHROUGH.md` for the end-to-end execution flow
- `docs/TROUBLESHOOTING.md` for common problems and solutions

Open an issue on GitHub for anything else.
