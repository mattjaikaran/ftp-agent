# FTP Agent - End-to-End Walkthrough

This document walks through a complete execution of the FTP Agent, from startup to migration report. It describes every step the autonomous agent takes, with concrete log examples, Copilot prompt excerpts, and API interactions.

---

## Prerequisites

Before the agent runs, the following must be in place:

- The `legacy-file-list.csv` file in the `config/` directory containing all ~1400 file entries
- A configured `appsettings.json` (or `appsettings.Development.json`) with API keys for Datadog, Octopus Deploy, and GitHub
- The `gh` CLI authenticated with appropriate scopes (`repo`, `workflow`, `read:org`)
- The target file ingestion repo cloned locally at the path specified in `GitHubConfig.TargetRepoPath`
- Prompt templates present at `prompts/config-translation.md` and `prompts/error-diagnosis.md`

---

## Step 1: Startup and State Initialization

When the agent starts, `Program.cs` builds the .NET host, wires up dependency injection, and hands control to the `BatchOrchestrator`.

The `StateStore` initializes the SQLite database at the path configured in `AgentConfig.StateDatabasePath` (default: `migration-state.db`). If the database does not exist, it creates the schema. If it already exists from a previous run, it picks up where it left off.

### Loading the File List

The agent reads `legacy-file-list.csv` and inserts every entry that is not already tracked into the SQLite `file_entries` table with status `Pending`.

```
[2026-02-07 08:00:01 INF] FTP Agent starting. DryRun=False, Environment=Development
[2026-02-07 08:00:01 INF] StateStore initialized at migration-state.db
[2026-02-07 08:00:02 INF] Loaded legacy file list from config/legacy-file-list.csv
[2026-02-07 08:00:02 INF] Total files in CSV: 1403
[2026-02-07 08:00:02 INF] Already tracked: 320 (247 succeeded, 53 in progress, 20 retry pending)
[2026-02-07 08:00:02 INF] New entries added: 0
[2026-02-07 08:00:02 INF] Pending files remaining: 1083
```

Each `FileEntry` record in SQLite tracks:

| Column | Example Value |
|---|---|
| `Id` | `file-0321` |
| `Name` | `daily-trades-report` |
| `LegacyConfig` | Raw semi-structured config blob |
| `NewConfig` | (empty until translated) |
| `Status` | `Pending` |
| `RetryCount` | `0` |
| `Protocol` | `SFTP` |
| `SourcePath` | `/legacy/configs/daily-trades-report.cfg` |
| `DestinationPath` | `/ingestion-app/configs/daily-trades-report.yaml` |

---

## Step 2: Batch Selection

The `BatchOrchestrator` queries the `StateStore` for the next batch. Batch size is controlled by `AgentConfig.BatchSize` (default: 10). Files with status `Pending` or `RetryPending` are eligible.

```
[2026-02-07 08:00:02 INF] Selecting next batch. BatchSize=10, MaxBatchesPerRun=0
[2026-02-07 08:00:02 INF] Batch 14 selected: 10 files
[2026-02-07 08:00:02 INF]   - file-0321 daily-trades-report (SFTP) [Pending]
[2026-02-07 08:00:02 INF]   - file-0322 eod-position-snapshot (SFTP) [Pending]
[2026-02-07 08:00:02 INF]   - file-0323 client-kyc-docs (SFTP, PGP) [Pending]
[2026-02-07 08:00:02 INF]   - file-0324 intraday-fx-rates (FTP) [Pending]
[2026-02-07 08:00:02 INF]   - file-0325 compliance-audit-log (Exchange) [Pending]
[2026-02-07 08:00:02 INF]   - file-0326 margin-call-notices (SFTP) [RetryPending, attempt 2]
[2026-02-07 08:00:02 INF]   - file-0327 settlement-instructions (SFTP) [Pending]
[2026-02-07 08:00:02 INF]   - file-0328 nav-daily-feed (SFTP) [Pending]
[2026-02-07 08:00:02 INF]   - file-0329 counterparty-ref-data (SFTP, PGP) [Pending]
[2026-02-07 08:00:02 INF]   - file-0330 risk-var-report (Exchange) [Pending]
```

Files marked `RetryPending` (like `file-0326` above) are files that failed in a previous batch but have not yet exhausted their retry limit (`MaxRetriesPerFile`, default: 3).

---

## Step 3: Config Translation

For each file in the batch, the `ConfigTranslator` sends the legacy config to Claude Opus 4.5 via the GitHub Copilot CLI. This is the core AI-powered step: the legacy configs are semi-structured and inconsistent, so a language model is needed to interpret them.

### How the Copilot Call Works

The `ConfigTranslator` constructs a prompt by loading the template from `prompts/config-translation.md` and injecting the legacy config. It then invokes the `gh copilot` CLI as a child process.

### Example Copilot Prompt (Config Translation)

The prompt template (`prompts/config-translation.md`) is rendered with the file's legacy config injected:

```markdown
You are a file ingestion configuration translator. Your job is to convert
legacy semi-structured file configuration into the new YAML-based config
format used by our Docker-based file ingestion application.

## Rules
- Preserve all connection details exactly (host, port, username, paths)
- Map legacy field names to the new schema (see mapping table below)
- If the legacy config mentions PGP, include the pgp_decryption section
- If the legacy config mentions a schedule, convert it to a cron expression
- Use the filename pattern from the legacy config to populate file_pattern
- Default to port 22 for SFTP if no port is specified
- Default to passive mode for FTP

## Field Mapping
| Legacy Field | New Field |
|---|---|
| ServerAddress / Host | connection.host |
| ServerPort / Port | connection.port |
| UserID / Username | connection.username |
| KeyFile / IdentityFile | connection.ssh_key_path |
| RemoteDir / SourcePath | connection.remote_path |
| FileNameMask / Pattern | file_pattern |
| PGPKeyFile | pgp_decryption.key_path |
| PGPPassphrase | pgp_decryption.passphrase_env_var |
| Schedule | schedule.cron |
| ArchiveAfterDownload | post_download.archive |

## Examples of Correct Translations

### Example 1: Basic SFTP
Legacy:
```
ServerAddress=sftp.acme.com
UserID=acme_user
KeyFile=/keys/acme_rsa
RemoteDir=/outbound/reports
FileNameMask=ACME_DAILY_*.csv
Schedule=Daily 06:00 UTC
```

New:
```yaml
name: acme-daily-report
protocol: sftp
connection:
  host: sftp.acme.com
  port: 22
  username: acme_user
  ssh_key_path: /keys/acme_rsa
  remote_path: /outbound/reports
file_pattern: "ACME_DAILY_*.csv"
schedule:
  cron: "0 6 * * *"
post_download:
  archive: false
```

### Example 2: SFTP with PGP
Legacy:
```
Host: sftp.bank.com
Port: 2222
Username: bank_svc
IdentityFile: /keys/bank_ed25519
SourcePath: /encrypted/
Pattern: BANK_EOD_*.pgp
PGPKeyFile: /pgp/bank_private.asc
PGPPassphrase: ENV:BANK_PGP_PASS
Schedule: Daily 23:30 UTC
ArchiveAfterDownload: Yes
```

New:
```yaml
name: bank-eod-encrypted
protocol: sftp
connection:
  host: sftp.bank.com
  port: 2222
  username: bank_svc
  ssh_key_path: /keys/bank_ed25519
  remote_path: /encrypted/
file_pattern: "BANK_EOD_*.pgp"
schedule:
  cron: "30 23 * * *"
pgp_decryption:
  key_path: /pgp/bank_private.asc
  passphrase_env_var: BANK_PGP_PASS
post_download:
  archive: true
```

---

## Now translate this legacy config:

```
${LEGACY_CONFIG}
```

Respond with ONLY the YAML configuration. No explanations, no markdown fences.
```

### What Happens Under the Hood

The `ConfigTranslator` calls the Copilot CLI like this (simplified):

```csharp
var process = Process.Start(new ProcessStartInfo
{
    FileName = copilotConfig.CliPath,  // "gh"
    Arguments = $"copilot --model {copilotConfig.Model}",
    RedirectStandardInput = true,
    RedirectStandardOutput = true
});
process.StandardInput.Write(renderedPrompt);
var yamlOutput = process.StandardOutput.ReadToEnd();
```

### Example Log Output

```
[2026-02-07 08:00:03 INF] Translating config for file-0321 (daily-trades-report)
[2026-02-07 08:00:05 INF] Copilot returned 24 lines of YAML for file-0321
[2026-02-07 08:00:05 INF] Translating config for file-0322 (eod-position-snapshot)
[2026-02-07 08:00:07 INF] Copilot returned 18 lines of YAML for file-0322
[2026-02-07 08:00:07 INF] Translating config for file-0323 (client-kyc-docs)
[2026-02-07 08:00:10 INF] Copilot returned 31 lines of YAML for file-0323 (includes PGP section)
...
[2026-02-07 08:00:28 INF] Config translation complete for batch 14. 10/10 files translated.
```

If translation fails for a specific file (for example, the legacy config is completely unreadable), the agent logs a warning and marks the file with `Status = Failed` and a `LastError` explaining the issue. The remaining files in the batch continue.

---

## Step 4: Writing Configs

The `NewConfigWriter` writes each translated YAML config to the target repository's config directory. The destination path is derived from the file entry's `DestinationPath` field.

```
[2026-02-07 08:00:28 INF] Writing 10 config files to /repos/file-ingestion-app/configs/
[2026-02-07 08:00:28 INF]   Written: /repos/file-ingestion-app/configs/daily-trades-report.yaml
[2026-02-07 08:00:28 INF]   Written: /repos/file-ingestion-app/configs/eod-position-snapshot.yaml
[2026-02-07 08:00:28 INF]   Written: /repos/file-ingestion-app/configs/client-kyc-docs.yaml
[2026-02-07 08:00:28 INF]   Written: /repos/file-ingestion-app/configs/intraday-fx-rates.yaml
[2026-02-07 08:00:28 INF]   Written: /repos/file-ingestion-app/configs/compliance-audit-log.yaml
[2026-02-07 08:00:28 INF]   Written: /repos/file-ingestion-app/configs/margin-call-notices.yaml (retry #2)
[2026-02-07 08:00:28 INF]   Written: /repos/file-ingestion-app/configs/settlement-instructions.yaml
[2026-02-07 08:00:28 INF]   Written: /repos/file-ingestion-app/configs/nav-daily-feed.yaml
[2026-02-07 08:00:28 INF]   Written: /repos/file-ingestion-app/configs/counterparty-ref-data.yaml
[2026-02-07 08:00:28 INF]   Written: /repos/file-ingestion-app/configs/risk-var-report.yaml
```

Each file's status is updated to `InProgress` in the SQLite state store at this point.

---

## Step 5: Git Commit and Push

The `GitManager` stages the new/modified config files, creates a commit with a descriptive message, and pushes to the remote.

### What the Agent Does

```csharp
// GitManager.CommitAndPushAsync
await RunGitCommand("add", "configs/");
await RunGitCommand("commit", "-m", $"migrate: batch {batchNumber} - {fileCount} files\n\nFiles: {fileNames}");
await RunGitCommand("push", "origin", branchName);
```

### Example Log Output

```
[2026-02-07 08:00:29 INF] GitManager: staging config changes
[2026-02-07 08:00:29 INF] GitManager: creating commit
[2026-02-07 08:00:29 INF] GitManager: commit created - a1b2c3d "migrate: batch 14 - 10 files"
[2026-02-07 08:00:30 INF] GitManager: pushing to origin/main
[2026-02-07 08:00:32 INF] GitManager: push successful. Commit a1b2c3d pushed to origin/main
```

The commit hash (`a1b2c3d`) is stored on each `FileEntry.CommitHash` and used to track the corresponding GitHub Actions workflow run.

---

## Step 6: GitHub Actions Build

After pushing, the `GitHubActionsMonitor` polls GitHub Actions to find and track the workflow run triggered by the push. It uses the `gh` CLI.

### Polling Logic

The monitor runs in a loop:

1. Call `gh run list --repo {repo} --branch {branch} --limit 5 --json databaseId,headSha,status,conclusion`
2. Find the run whose `headSha` matches the commit hash from step 5
3. If the run is still `in_progress` or `queued`, wait `PollIntervalSeconds` (default: 30s) and check again
4. Continue until the run completes or `CiBuildTimeoutMinutes` (default: 20 min) is exceeded

### Example Log Output (Successful Build)

```
[2026-02-07 08:00:33 INF] GitHubActionsMonitor: looking for workflow run for commit a1b2c3d
[2026-02-07 08:00:33 INF] GitHubActionsMonitor: found run #4821 (status=queued)
[2026-02-07 08:01:03 INF] GitHubActionsMonitor: run #4821 status=in_progress (elapsed: 30s)
[2026-02-07 08:01:33 INF] GitHubActionsMonitor: run #4821 status=in_progress (elapsed: 60s)
[2026-02-07 08:02:03 INF] GitHubActionsMonitor: run #4821 status=in_progress (elapsed: 90s)
...
[2026-02-07 08:08:33 INF] GitHubActionsMonitor: run #4821 status=completed, conclusion=success (elapsed: 8m00s)
[2026-02-07 08:08:33 INF] Build succeeded. Docker image built and pushed to registry.
```

### Example Log Output (Failed Build)

```
[2026-02-07 08:08:33 ERR] GitHubActionsMonitor: run #4821 status=completed, conclusion=failure (elapsed: 6m30s)
[2026-02-07 08:08:33 WRN] Build failed. Fetching build logs for diagnosis...
[2026-02-07 08:08:35 INF] DiagnosticEngine: analyzing build failure logs (142 lines)
[2026-02-07 08:08:38 INF] DiagnosticEngine diagnosis: "YAML syntax error in client-kyc-docs.yaml line 14: unexpected key 'pgp_decrytion' (typo). Should be 'pgp_decryption'."
[2026-02-07 08:08:38 INF] Applying build fix for file-0323 (client-kyc-docs)
```

When a build fails, the `DiagnosticEngine` is called immediately. It sends the build logs to Claude Opus 4.5 via Copilot, which identifies the root cause. The agent then applies the fix, re-commits, and loops back to step 5.

---

## Step 7: Octopus Deployment

Once the Docker image is built, the agent triggers a deployment via the Octopus Deploy REST API.

### API Interaction

The `OctopusDeployClient` makes the following REST calls:

1. `GET /api/{spaceId}/projects/{projectName}` -- Get project ID
2. `GET /api/{spaceId}/environments?name={envName}` -- Get environment ID
3. `POST /api/{spaceId}/deployments` -- Create deployment with the new release/version
4. `GET /api/{spaceId}/tasks/{taskId}` -- Poll deployment task status

### Example Log Output

```
[2026-02-07 08:08:34 INF] OctopusDeployClient: triggering deployment for project "FileIngestionApp" to environment "Development"
[2026-02-07 08:08:35 INF] OctopusDeployClient: deployment created. TaskId=ServerTasks-28491
[2026-02-07 08:08:35 INF] OctopusDeployClient: polling deployment status...
[2026-02-07 08:09:05 INF] OctopusDeployClient: task ServerTasks-28491 state=Executing (elapsed: 30s)
[2026-02-07 08:09:35 INF] OctopusDeployClient: task ServerTasks-28491 state=Executing (elapsed: 60s)
...
[2026-02-07 08:12:05 INF] OctopusDeployClient: task ServerTasks-28491 state=Success (elapsed: 3m30s)
[2026-02-07 08:12:05 INF] Deployment succeeded. Application is running with new configs.
```

The deployment ID is stored on each `FileEntry.DeploymentId` for traceability.

If the deployment fails (e.g., health check fails, environment locked), the agent logs the error and either retries the deployment or moves to error diagnosis depending on the failure type.

---

## Step 8: Datadog Monitoring

After deployment succeeds, the agent waits for files to start downloading. The wait period is configurable via `AgentConfig.DatadogCheckDelayMinutes` (default: 5 minutes). This buffer allows the newly deployed container to pick up the configs, connect to SFTP servers, and generate log entries.

### Querying Datadog Logs API

The `DatadogClient` queries the Datadog Logs API for each file's identifier within the configured time window (`LogQueryWindowMinutes`, default: 15 minutes).

The API call looks like:

```http
POST https://api.datadoghq.com/api/v2/logs/events/search
Headers:
  DD-API-KEY: {apiKey}
  DD-APPLICATION-KEY: {appKey}
Body:
{
  "filter": {
    "query": "service:{serviceName} @file_name:daily-trades-report",
    "from": "now-15m",
    "to": "now"
  },
  "sort": "timestamp",
  "page": { "limit": 100 }
}
```

### Example Log Output

```
[2026-02-07 08:12:06 INF] Waiting 5 minutes for files to begin processing...
[2026-02-07 08:17:06 INF] DatadogClient: querying logs for 10 files (window: last 15 minutes)
[2026-02-07 08:17:07 INF] DatadogClient: file-0321 (daily-trades-report) - 12 log entries found
[2026-02-07 08:17:07 INF] DatadogClient: file-0322 (eod-position-snapshot) - 8 log entries found
[2026-02-07 08:17:07 INF] DatadogClient: file-0323 (client-kyc-docs) - 15 log entries found
[2026-02-07 08:17:08 INF] DatadogClient: file-0324 (intraday-fx-rates) - 0 log entries found
[2026-02-07 08:17:08 INF] DatadogClient: file-0325 (compliance-audit-log) - 6 log entries found
[2026-02-07 08:17:08 INF] DatadogClient: file-0326 (margin-call-notices) - 9 log entries found
[2026-02-07 08:17:08 INF] DatadogClient: file-0327 (settlement-instructions) - 4 log entries found
[2026-02-07 08:17:08 INF] DatadogClient: file-0328 (nav-daily-feed) - 7 log entries found
[2026-02-07 08:17:09 INF] DatadogClient: file-0329 (counterparty-ref-data) - 11 log entries found
[2026-02-07 08:17:09 INF] DatadogClient: file-0330 (risk-var-report) - 5 log entries found
```

---

## Step 9: Success/Failure Determination

For each file, the agent examines the returned Datadog log entries and classifies the outcome.

**Success patterns** (configurable in `DatadogConfig.SuccessLogPattern`):
- `"File downloaded successfully"`
- `"Upload to S3 completed"`
- `"SQS notification sent"`

**Failure patterns**:
- `"ERROR"` or `"FATAL"` level log entries
- `"Connection refused"`, `"Authentication failed"`, `"Permission denied"`
- `"PGP decryption failed"`, `"Key format not recognized"`
- No log entries at all (file was not picked up)

### Example Log Output

```
[2026-02-07 08:17:09 INF] Evaluating results for batch 14...
[2026-02-07 08:17:09 INF]   file-0321 (daily-trades-report): SUCCESS - "File downloaded successfully, uploaded to S3"
[2026-02-07 08:17:09 INF]   file-0322 (eod-position-snapshot): SUCCESS - "File downloaded successfully, uploaded to S3"
[2026-02-07 08:17:09 ERR]   file-0323 (client-kyc-docs): FAILED - "PGP decryption failed: unable to load private key at /pgp/kyc_private.asc"
[2026-02-07 08:17:09 WRN]   file-0324 (intraday-fx-rates): NO LOGS - file may not have been picked up
[2026-02-07 08:17:09 INF]   file-0325 (compliance-audit-log): SUCCESS - "Email attachment downloaded, uploaded to S3"
[2026-02-07 08:17:09 ERR]   file-0326 (margin-call-notices): FAILED - "SFTP authentication failed: key format not recognized (PuTTY PPK format)"
[2026-02-07 08:17:09 INF]   file-0327 (settlement-instructions): SUCCESS - "File downloaded successfully, uploaded to S3"
[2026-02-07 08:17:09 INF]   file-0328 (nav-daily-feed): SUCCESS - "File downloaded successfully, uploaded to S3"
[2026-02-07 08:17:09 ERR]   file-0329 (counterparty-ref-data): FAILED - "PGP decryption failed: incorrect passphrase"
[2026-02-07 08:17:09 INF]   file-0330 (risk-var-report): SUCCESS - "Email attachment downloaded, uploaded to S3"
[2026-02-07 08:17:09 INF] Batch 14 results: 6 succeeded, 3 failed, 1 no data
```

Files that succeeded are immediately marked `Status = Success` in the state store. They are done permanently.

---

## Step 10: Error Diagnosis

For each failed file, the `DiagnosticEngine` sends the error logs and the current config to Claude Opus 4.5 via Copilot for analysis.

### Example Copilot Prompt (Error Diagnosis)

The prompt template (`prompts/error-diagnosis.md`) is rendered with the file's error context:

```markdown
You are a DevOps diagnostic assistant specializing in file ingestion systems.
A file download configuration is failing in production. Analyze the error logs
and current configuration, then suggest a specific fix.

## Known Common Issues
1. PGP key path is wrong or the key file does not exist at the specified path
2. PGP passphrase environment variable is not set or has the wrong name
3. SFTP private key is in PuTTY PPK format but the application expects OpenSSH format
4. SFTP host key verification is failing (new host, changed key)
5. Remote directory path has a trailing slash mismatch
6. File pattern uses wrong glob syntax (regex vs glob)
7. Cron schedule specifies a time when the file is not yet available on the server
8. FTP passive mode is not enabled for servers behind NAT
9. Exchange mailbox folder path is case-sensitive
10. Connection timeout is too short for large files

## Current Configuration
```yaml
${CURRENT_CONFIG}
```

## Datadog Error Logs
```
${ERROR_LOGS}
```

## File Metadata
- Name: ${FILE_NAME}
- Protocol: ${PROTOCOL}
- Retry attempt: ${RETRY_COUNT} of ${MAX_RETRIES}

## Instructions
1. Identify the root cause from the error logs
2. Explain what is wrong in one sentence
3. Provide the corrected YAML configuration
4. If the issue is environmental (e.g., missing key file, wrong permissions),
   state that clearly -- the config change alone may not fix it

Respond in this exact format:
ROOT_CAUSE: <one sentence>
IS_RECOVERABLE: <true/false>
CHANGES:
- field: <dotted.path.to.field>
  old_value: <current value>
  new_value: <corrected value>
REVISED_CONFIG:
<full corrected YAML>
```

### Example Diagnosis: PGP Key Path Wrong

For `file-0323` (client-kyc-docs), the Datadog logs showed:

```
2026-02-07 08:15:32 ERROR PGP decryption failed: unable to load private key at /pgp/kyc_private.asc
2026-02-07 08:15:32 ERROR FileNotFoundException: /pgp/kyc_private.asc does not exist
2026-02-07 08:15:32 INFO  Available PGP keys in /pgp/: client_kyc_docs.asc, bank_private.asc
```

Claude Opus 4.5 responds:

```
ROOT_CAUSE: The PGP private key path is set to /pgp/kyc_private.asc but the actual file on disk is /pgp/client_kyc_docs.asc
IS_RECOVERABLE: true
CHANGES:
- field: pgp_decryption.key_path
  old_value: /pgp/kyc_private.asc
  new_value: /pgp/client_kyc_docs.asc
REVISED_CONFIG:
name: client-kyc-docs
protocol: sftp
connection:
  host: sftp.client-kyc.com
  port: 22
  username: kyc_svc
  ssh_key_path: /keys/kyc_ed25519
  remote_path: /outbound/encrypted/
file_pattern: "KYC_DOCS_*.pgp"
schedule:
  cron: "0 7 * * *"
pgp_decryption:
  key_path: /pgp/client_kyc_docs.asc
  passphrase_env_var: KYC_PGP_PASSPHRASE
post_download:
  archive: true
```

### Example Diagnosis: SFTP Key Format Mismatch

For `file-0326` (margin-call-notices), this is retry attempt 2. The Datadog logs showed:

```
2026-02-07 08:16:01 ERROR SFTP authentication failed for host margin-sftp.broker.com
2026-02-07 08:16:01 ERROR Key format not recognized: /keys/margin_calls.ppk
2026-02-07 08:16:01 ERROR Expected OpenSSH format, got PuTTY PPK format
```

Claude Opus 4.5 responds:

```
ROOT_CAUSE: The SSH private key at /keys/margin_calls.ppk is in PuTTY PPK format but the application requires OpenSSH format
IS_RECOVERABLE: false
CHANGES:
- field: connection.ssh_key_path
  old_value: /keys/margin_calls.ppk
  new_value: /keys/margin_calls_openssh
NOTE: This requires a manual step. Convert the key using: puttygen /keys/margin_calls.ppk -O private-openssh -o /keys/margin_calls_openssh
```

When the diagnosis says `IS_RECOVERABLE: false`, the agent logs a warning and flags this file for manual intervention. It does not retry automatically.

### Example Log Output

```
[2026-02-07 08:17:10 INF] DiagnosticEngine: analyzing failure for file-0323 (client-kyc-docs)
[2026-02-07 08:17:13 INF] DiagnosticEngine: root cause = "PGP key path mismatch". Recoverable=true.
[2026-02-07 08:17:13 INF] DiagnosticEngine: suggested fix: pgp_decryption.key_path /pgp/kyc_private.asc -> /pgp/client_kyc_docs.asc
[2026-02-07 08:17:14 INF] DiagnosticEngine: analyzing failure for file-0324 (intraday-fx-rates)
[2026-02-07 08:17:17 WRN] DiagnosticEngine: no logs found for file-0324. Possible causes: wrong file_pattern, schedule has not triggered yet, or config not loaded.
[2026-02-07 08:17:18 INF] DiagnosticEngine: analyzing failure for file-0326 (margin-call-notices)
[2026-02-07 08:17:21 WRN] DiagnosticEngine: root cause = "PuTTY PPK key format". Recoverable=false. Requires manual key conversion.
[2026-02-07 08:17:22 INF] DiagnosticEngine: analyzing failure for file-0329 (counterparty-ref-data)
[2026-02-07 08:17:25 INF] DiagnosticEngine: root cause = "Wrong PGP passphrase env var". Recoverable=true.
```

---

## Step 11: Config Fix and Retry

For recoverable failures, the agent applies the suggested config changes and queues the files for retry.

### What Happens

1. The `NewConfigWriter.ApplyFixAsync()` method updates the YAML config file with the changes from the diagnosis
2. The `StateStore` increments the file's `RetryCount` and sets status to `RetryPending`
3. On the next iteration of the batch loop, these files will be included in a new batch (they go back to step 5: commit, push, build, deploy, check)

### Example Log Output

```
[2026-02-07 08:17:25 INF] Applying fixes for recoverable failures...
[2026-02-07 08:17:25 INF]   file-0323: updated pgp_decryption.key_path. Retry 1/3 queued.
[2026-02-07 08:17:25 INF]   file-0324: config looks correct, adjusting schedule for earlier window. Retry 1/3 queued.
[2026-02-07 08:17:25 WRN]   file-0326: NOT recoverable (key format). Marked as FAILED after 2 attempts. Needs manual intervention.
[2026-02-07 08:17:25 INF]   file-0329: updated pgp_decryption.passphrase_env_var. Retry 1/3 queued.
[2026-02-07 08:17:25 INF] Batch 14 summary: 6 succeeded, 1 permanently failed, 3 queued for retry
```

The retry loop then proceeds. The agent commits the fixed configs, pushes, waits for the build, deploys, and checks Datadog again. This cycle repeats until the file succeeds or hits `MaxRetriesPerFile`.

### Retry Cycle Example (file-0323, attempt 2)

```
[2026-02-07 08:17:26 INF] Starting retry cycle for 3 files...
[2026-02-07 08:17:26 INF] GitManager: commit b4e5f6a "fix: batch 14 retry - 3 files (PGP path, schedule, passphrase)"
[2026-02-07 08:17:28 INF] GitManager: push successful
[2026-02-07 08:17:28 INF] GitHubActionsMonitor: waiting for build...
[2026-02-07 08:24:30 INF] GitHubActionsMonitor: build succeeded (7m02s)
[2026-02-07 08:24:31 INF] OctopusDeployClient: deploying...
[2026-02-07 08:28:01 INF] OctopusDeployClient: deployment succeeded (3m30s)
[2026-02-07 08:28:01 INF] Waiting 5 minutes for log propagation...
[2026-02-07 08:33:01 INF] DatadogClient: checking retry files...
[2026-02-07 08:33:02 INF]   file-0323 (client-kyc-docs): SUCCESS - "PGP decryption succeeded, file uploaded to S3"
[2026-02-07 08:33:02 INF]   file-0324 (intraday-fx-rates): SUCCESS - "File downloaded successfully"
[2026-02-07 08:33:02 ERR]   file-0329 (counterparty-ref-data): FAILED - "PGP decryption failed: incorrect passphrase"
[2026-02-07 08:33:02 INF] Retry cycle results: 2 succeeded, 1 still failing (attempt 2/3)
```

---

## Step 12: Completion and Migration Report

When all files have been processed (either succeeded, permanently failed, or hit max retries), the `BatchOrchestrator` exits the main loop and generates a `MigrationReport`.

### Example Final Log Output

```
[2026-02-07 14:45:00 INF] ============================================
[2026-02-07 14:45:00 INF] Migration Report - 2026-02-07 14:45:00 UTC
[2026-02-07 14:45:00 INF] ============================================
[2026-02-07 14:45:00 INF] Total Files:    1403
[2026-02-07 14:45:00 INF] Succeeded:      1361 (97.0%)
[2026-02-07 14:45:00 INF] Failed:         42
[2026-02-07 14:45:00 INF] Pending:        0
[2026-02-07 14:45:00 INF] In Progress:    0
[2026-02-07 14:45:00 INF] Retry Pending:  0
[2026-02-07 14:45:00 INF] Duration:       6h 45m 00s
[2026-02-07 14:45:00 INF] Batches:        142
[2026-02-07 14:45:00 INF] ============================================
[2026-02-07 14:45:00 INF] Failed files requiring manual intervention:
[2026-02-07 14:45:00 INF]   file-0326 margin-call-notices: PuTTY PPK key format (needs conversion)
[2026-02-07 14:45:00 INF]   file-0329 counterparty-ref-data: PGP passphrase unknown (needs credential update)
[2026-02-07 14:45:00 INF]   file-0501 legacy-archive-feed: Server decommissioned (SFTP host unreachable)
[2026-02-07 14:45:00 INF]   ... (39 more)
[2026-02-07 14:45:00 INF] Full report written to migration-report-2026-02-07.json
[2026-02-07 14:45:00 INF] FTP Agent completed successfully
```

The report is also persisted as a JSON file for offline analysis. Each failed entry includes the full diagnosis history, all retry attempts, and the last known error.

---

## Summary of the Full Loop

```
                      +---------------------------+
                      |  1. Load file list (CSV)  |
                      |     -> SQLite state store  |
                      +------------+--------------+
                                   |
                      +------------v--------------+
                      |  2. Select next batch (N)  |
                      +------------+--------------+
                                   |
                      +------------v--------------+
                      |  3. Translate configs      |
                      |     (Opus 4.5 via Copilot) |
                      +------------+--------------+
                                   |
                      +------------v--------------+
                      |  4. Write config files     |
                      +------------+--------------+
                                   |
               +----->+------------v--------------+
               |      |  5. Git commit & push      |
               |      +------------+--------------+
               |                   |
               |      +------------v--------------+
               |      |  6. GitHub Actions build   |
               |      |     (poll until done)      |
               |      +------------+--------------+
               |                   |
               |      +------------v--------------+
               |      |  7. Octopus deployment     |
               |      |     (trigger + poll)       |
               |      +------------+--------------+
               |                   |
               |      +------------v--------------+
               |      |  8. Wait + check Datadog   |
               |      +------------+--------------+
               |                   |
               |      +------------v--------------+
               |      |  9. Classify success/fail  |
               |      +-----+------+---------+----+
               |            |      |         |
               |         success  fail    max retries
               |            |      |         |
               |         +--v--+   |      +--v--+
               |         |DONE |   |      |FAIL |
               |         +-----+   |      +-----+
               |                   |
               |      +------------v--------------+
               |      | 10. Diagnose with Opus 4.5 |
               |      +------------+--------------+
               |                   |
               |      +------------v--------------+
               |      | 11. Apply fix, inc retry   |
               +------+     Loop back to step 5    |
                      +---------------------------+

              When all files processed:
                      +---------------------------+
                      | 12. Generate report        |
                      +---------------------------+
```

---

## Dry-Run Mode

When the agent is started with `--dry-run`, several behaviors change:

- The `StubDeploymentClient` is injected instead of `OctopusDeployClient`. It simulates successful deployments with a short delay.
- Git operations still execute against a local branch but do not push to the remote.
- Datadog queries are skipped; all files are reported as "success" by the stub.
- Config translation still runs against Copilot (to validate prompt quality).

This mode is useful for testing the translation pipeline without affecting production infrastructure.

```bash
dotnet run --project src/FtpAgent -- --dry-run
```

---

## Environment Variables

All configuration values can be overridden via environment variables with the `FTPAGENT_` prefix. Nested keys use double underscores:

```bash
export FTPAGENT_Agent__BatchSize=5
export FTPAGENT_Datadog__ApiKey=your-api-key
export FTPAGENT_OctopusDeploy__ApiKey=your-octopus-key
```

This is useful for CI environments or when running on a VM where you do not want secrets in config files.
