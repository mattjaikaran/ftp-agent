# FTP Agent - Troubleshooting Guide

This guide covers common problems encountered when running the FTP Agent, organized by symptom. Each section includes the symptom, likely cause, step-by-step solution, and prevention measures.

---

## Table of Contents

1. [Agent Hangs on GitHub Actions](#1-agent-hangs-on-github-actions)
2. [Datadog Returns No Logs](#2-datadog-returns-no-logs)
3. [Octopus Deployment Fails](#3-octopus-deployment-fails)
4. [Config Translation Produces Bad Output](#4-config-translation-produces-bad-output)
5. [Error Diagnosis Suggests Wrong Fix](#5-error-diagnosis-suggests-wrong-fix)
6. [SQLite State Corruption](#6-sqlite-state-corruption)
7. [Git Push Rejected](#7-git-push-rejected)
8. [Copilot CLI Not Responding](#8-copilot-cli-not-responding)
9. [Files Download but Wrong Content](#9-files-download-but-wrong-content)
10. [Agent Keeps Retrying the Same Error](#10-agent-keeps-retrying-the-same-error)

---

## 1. Agent Hangs on GitHub Actions

### Symptom

The agent appears to freeze after pushing a commit. Log output stops at a line like:

```
[2026-02-07 08:01:03 INF] GitHubActionsMonitor: polling for workflow run for commit a1b2c3d...
```

No further output appears for many minutes, eventually ending with:

```
[2026-02-07 08:21:03 ERR] GitHubActionsMonitor: timed out waiting for workflow run (CiBuildTimeoutMinutes=20)
```

### Likely Cause

**The workflow was never triggered.** This can happen for several reasons:

- The push went to a branch that does not have a workflow trigger configured (e.g., the workflow only runs on `main` but the agent pushed to a feature branch).
- GitHub Actions is disabled for the repository.
- The workflow YAML file has a syntax error introduced by a recent change, so GitHub silently refuses to run it.
- GitHub is experiencing an outage or delayed queue processing.
- The commit hash the agent is looking for does not match any workflow run because the push was rejected or silently dropped.

### Solution

1. **Verify the workflow was triggered** by checking GitHub directly:
   ```bash
   gh run list --repo owner/repo --branch main --limit 5
   ```
   If no recent run appears, the workflow was not triggered.

2. **Check that the workflow file is valid:**
   ```bash
   gh workflow view build.yml --repo owner/repo
   ```
   If this errors, the workflow YAML has a syntax problem.

3. **Check the push actually landed:**
   ```bash
   git log --oneline origin/main -5
   ```
   Confirm the commit hash matches what the agent logged.

4. **Check GitHub Actions status:**
   Visit https://www.githubstatus.com/ to verify there is no ongoing incident affecting Actions.

5. **Increase the timeout** if builds legitimately take longer than expected. Update `appsettings.json`:
   ```json
   {
     "Agent": {
       "CiBuildTimeoutMinutes": 30
     }
   }
   ```

6. **Manually trigger the workflow** if needed:
   ```bash
   gh workflow run build.yml --repo owner/repo --ref main
   ```

### Prevention

- Set `CiBuildTimeoutMinutes` to at least 1.5x your typical build time.
- Add a health check in CI that verifies the workflow file parses correctly.
- Monitor the repository's Actions tab periodically for queued/stuck runs.
- Confirm the workflow's `on:` trigger matches the branch the agent pushes to.

---

## 2. Datadog Returns No Logs

### Symptom

After a successful deployment, the agent queries Datadog but finds zero log entries for one or more files:

```
[2026-02-07 08:17:08 WRN] DatadogClient: file-0324 (intraday-fx-rates) - 0 log entries found
```

All files in the batch show zero logs, or specific files consistently show no data.

### Likely Cause

There are multiple possible causes:

**Wrong time window:** The `DatadogCheckDelayMinutes` or `LogQueryWindowMinutes` values may not align with when the application actually processes files. If the application runs on a schedule (e.g., every hour), the logs may not appear within the query window.

**Wrong service name:** The `Datadog.ServiceName` in configuration does not match the `service` tag on the application's logs in Datadog.

**Wrong query filter:** The file identifier used in the Datadog query does not match the field the application logs. For example, the agent queries for `@file_name:intraday-fx-rates` but the application logs `@config_id:FILE-0324`.

**API permissions:** The Datadog Application Key does not have permission to query logs, or the API Key is for the wrong Datadog organization.

**Logs not indexed:** The application's logs may be going to a Datadog log pipeline that excludes them from the default index, or they are routed to a custom index the query does not target.

### Solution

1. **Verify logs exist in Datadog manually.** Open the Datadog Logs Explorer in your browser and search for the file using the same time window:
   ```
   service:your-service-name @file_name:intraday-fx-rates
   ```

2. **Check the service name** in your Datadog Logs Explorer. Filter by `service:*` and look at what service names appear. Update `appsettings.json` if mismatched:
   ```json
   {
     "Datadog": {
       "ServiceName": "file-ingestion-app"
     }
   }
   ```

3. **Widen the time window.** If the application has processing delays, increase the delay and query window:
   ```json
   {
     "Agent": {
       "DatadogCheckDelayMinutes": 10,
       "LogQueryWindowMinutes": 30
     }
   }
   ```

4. **Verify API permissions** by running a direct API test:
   ```bash
   curl -X POST "https://api.datadoghq.com/api/v2/logs/events/search" \
     -H "DD-API-KEY: your-api-key" \
     -H "DD-APPLICATION-KEY: your-app-key" \
     -H "Content-Type: application/json" \
     -d '{"filter":{"query":"service:file-ingestion-app","from":"now-1h","to":"now"},"page":{"limit":10}}'
   ```
   If this returns an error, the credentials are wrong or lack permissions.

5. **Check if the file's schedule has triggered.** Some files only download at specific times. If the file's cron schedule has not fired since the deployment, no logs will exist.

### Prevention

- Verify `ServiceName` against Datadog before first run.
- Start with generous time windows (`DatadogCheckDelayMinutes: 10`, `LogQueryWindowMinutes: 30`) and tighten later.
- Test the Datadog API credentials manually before configuring the agent.
- Consider files with cron schedules that fire infrequently -- these may need a longer wait or a different verification approach.

---

## 3. Octopus Deployment Fails

### Symptom

The agent triggers a deployment but it fails:

```
[2026-02-07 08:12:05 ERR] OctopusDeployClient: task ServerTasks-28491 state=Failed
[2026-02-07 08:12:05 ERR] Deployment failed: "Release 2.1.47 cannot be deployed to Development: environment is locked"
```

Or the deployment creation call itself returns an error.

### Likely Cause

**Version/release mismatch:** The Octopus project does not have a release matching the Docker image tag that was just built. The release may need to be created first.

**Environment locked:** Another deployment is in progress, or the environment has been manually locked by an operator.

**API authentication error:** The Octopus API key has expired, lacks permissions for the project or environment, or is for the wrong Octopus space.

**Project or environment renamed:** The project name or environment name in configuration no longer matches what exists in Octopus.

**Health check failure:** The deployment itself ran, but the post-deployment health check failed (e.g., the container crashes on startup due to a bad config).

### Solution

1. **Check the Octopus dashboard** for the specific deployment task. The task log will show the exact failure reason.

2. **For locked environments**, wait for the current deployment to finish, or manually unlock:
   ```
   Octopus Dashboard -> Environments -> Development -> Unlock
   ```

3. **For version mismatches**, verify the release exists:
   ```bash
   curl -H "X-Octopus-ApiKey: $OCTOPUS_API_KEY" \
     "$OCTOPUS_URL/api/Spaces-1/projects/FileIngestionApp/releases?take=5"
   ```

4. **For API authentication errors**, verify the API key:
   ```bash
   curl -H "X-Octopus-ApiKey: $OCTOPUS_API_KEY" \
     "$OCTOPUS_URL/api/users/me"
   ```
   If this returns a 401, regenerate the API key in Octopus.

5. **For health check failures**, examine the deployment task log in Octopus. The container likely crashed on startup. Check:
   - Is the YAML config syntactically valid?
   - Are all required environment variables set in the Kubernetes deployment?
   - Does the container image exist in the registry?

6. **Retry the deployment** manually to rule out transient issues:
   ```bash
   # The agent will retry automatically on the next batch iteration
   # Or manually reset the file state:
   sqlite3 migration-state.db "UPDATE file_entries SET Status = 4 WHERE Status = 1;"
   ```

### Prevention

- Ensure the Octopus API key has the `DeploymentCreate` and `TaskView` permissions for the target project and environment.
- Set `DeployWaitTimeoutMinutes` high enough for your typical deployment duration (default: 30 min).
- Coordinate with team members to avoid concurrent deployments to the same environment during migration runs.
- Add a pre-deployment check in the agent that verifies the environment is not locked before triggering.

---

## 4. Config Translation Produces Bad Output

### Symptom

The translated YAML config is syntactically valid but semantically wrong. Examples:

- SFTP port set to `21` (FTP default) instead of `22`
- PGP section missing even though the legacy config mentions encryption
- File pattern uses regex syntax instead of glob syntax
- Schedule cron expression is wrong (e.g., daily at midnight instead of 6 AM)
- Fields from the legacy config are silently dropped

The agent deploys the bad config, the file fails in Datadog, and the diagnostic engine may or may not catch the root cause.

### Likely Cause

**Insufficient examples in the prompt.** The `config-translation.md` prompt template may not include an example that covers the specific pattern the LLM encountered.

**Ambiguous legacy config.** The legacy config uses non-standard field names or formats that the LLM misinterprets. For example, `Schedule=Daily 6 AM EST` could be interpreted multiple ways.

**Prompt too long or unfocused.** If the prompt template has grown very large, the LLM may lose focus on specific instructions buried in the middle.

**Model temperature or randomness.** The LLM may produce slightly different output each time it runs, especially for ambiguous inputs.

### Solution

1. **Identify the specific failure** by comparing the legacy config, the translated config, and the Datadog error:
   ```bash
   # View the legacy config
   sqlite3 migration-state.db "SELECT LegacyConfig FROM file_entries WHERE Id = 'file-0324';"

   # View the translated config
   cat /repos/file-ingestion-app/configs/intraday-fx-rates.yaml
   ```

2. **Add a new example to the prompt.** Open `prompts/config-translation.md` and add a new example that covers this pattern. Place the example near the top of the examples section (LLMs pay more attention to early examples):

   ```markdown
   ### Example 3: FTP with Non-Standard Schedule Format
   Legacy:
   ```
   Host: ftp.vendor.com
   Protocol: FTP
   Schedule: Daily 6 AM EST
   FileNameMask: RATES_*.csv
   ```

   New:
   ```yaml
   name: vendor-rates
   protocol: ftp
   connection:
     host: ftp.vendor.com
     port: 21
     passive_mode: true
   file_pattern: "RATES_*.csv"
   schedule:
     cron: "0 11 * * *"  # 6 AM EST = 11 AM UTC
   ```
   ```

3. **Add explicit instructions** for the mishandled case. If the LLM keeps defaulting SFTP port to 21, add a rule:
   ```markdown
   ## Rules
   - Default to port 22 for SFTP if no port is specified
   - Default to port 21 for FTP if no port is specified
   - SFTP and FTP are different protocols with different default ports
   ```

4. **Test the updated prompt** on the files that failed:
   ```bash
   FTPAGENT_Agent__BatchSize=1 dotnet run --project src/FtpAgent/FtpAgent.csproj -- --dry-run
   ```

### Prevention

- After every translation failure that is caused by a prompt deficiency, add a corrective example to the prompt. This builds an ever-improving prompt over time.
- Review the first batch of translations manually before deploying.
- Consider adding a YAML schema validation step in `NewConfigWriter` that rejects configs with obviously wrong values (e.g., port 0, empty host).
- Keep the prompt template under ~2000 words. If it grows too large, move supplementary reference material to a separate section that the LLM can refer to but is not in the critical path.

---

## 5. Error Diagnosis Suggests Wrong Fix

### Symptom

The `DiagnosticEngine` analyzes Datadog error logs and suggests a config change, but the suggested fix does not resolve the issue. The file fails again on retry with the same or a different error.

```
[2026-02-07 08:17:13 INF] DiagnosticEngine: root cause = "Wrong remote path". Recoverable=true.
[2026-02-07 08:17:13 INF] DiagnosticEngine: suggested fix: connection.remote_path /outbound/ -> /outbound/reports/
# ... after retry ...
[2026-02-07 08:33:02 ERR] file-0328: FAILED - "Connection refused: port 22"
# The actual issue was the SFTP server uses port 2222, not a path issue
```

### Likely Cause

**Missing context in the diagnosis prompt.** The `error-diagnosis.md` prompt does not include enough known error patterns, so the LLM guesses incorrectly.

**Error logs are ambiguous.** The Datadog logs may not contain enough detail for the LLM to pinpoint the issue. For example, a generic "Connection failed" log does not distinguish between wrong port, wrong host, firewall block, or DNS failure.

**The LLM fixates on the first plausible explanation** rather than considering all possibilities.

**The real issue is environmental**, not configuration-based (e.g., firewall rule, expired certificate, server downtime).

### Solution

1. **Add the error pattern to the diagnosis prompt.** Open `prompts/error-diagnosis.md` and add the specific error-to-fix mapping:

   ```markdown
   ## Known Common Issues
   ...
   11. "Connection refused" on SFTP usually means wrong port, not wrong host.
       Check if the legacy config specifies a non-standard port (2222, 2022, etc.)
       before assuming the host is wrong.
   ```

2. **Improve the error log query.** The `DatadogClient` may need to fetch more log lines or include additional context fields. Check if the application logs connection details (host, port, username) that could disambiguate:

   ```json
   {
     "filter": {
       "query": "service:file-ingestion-app @file_name:nav-daily-feed status:error",
       "from": "now-15m",
       "to": "now"
     },
     "page": { "limit": 200 }
   }
   ```

3. **Add a validation step.** After the LLM suggests a fix, have the agent compare the suggested config against the original legacy config. If the LLM changed a field that was already correctly translated, flag it for review.

4. **Manually diagnose and fix** the file, then add the pattern to the prompt so future occurrences are handled correctly:
   ```bash
   # Manually fix the config
   vim /repos/file-ingestion-app/configs/nav-daily-feed.yaml

   # Mark the file for retry
   sqlite3 migration-state.db "UPDATE file_entries SET Status = 4, RetryCount = 0 WHERE Id = 'file-0328';"
   ```

### Prevention

- Maintain a growing list of known error patterns in `prompts/error-diagnosis.md`. Every time a misdiagnosis occurs, add the correct mapping.
- Include the original legacy config in the diagnosis prompt (the agent already does this) so the LLM can cross-reference.
- Consider adding a confidence score to the diagnosis output. If the LLM is uncertain, flag the file for manual review instead of applying a potentially wrong fix.
- Set `MaxRetriesPerFile` to a reasonable value (default: 3) to prevent infinite wrong-fix loops.

---

## 6. SQLite State Corruption

### Symptom

The agent crashes on startup or during a batch with a SQLite-related error:

```
[2026-02-07 08:00:01 CRI] FTP Agent terminated with an unhandled exception
Microsoft.Data.Sqlite.SqliteException: database disk image is malformed
```

Or file counts do not add up:

```
[2026-02-07 08:00:02 WRN] State inconsistency: 1403 files in CSV but 1397 in database
```

Or files are stuck in `InProgress` status from a previous crashed run:

```
[2026-02-07 08:00:02 WRN] Found 15 files stuck in InProgress status from a previous run
```

### Likely Cause

**Process killed during a write.** If the agent was killed with `kill -9` or the machine lost power during a SQLite write transaction, the database file can become corrupted.

**Concurrent access.** Two instances of the agent are running against the same database file simultaneously. SQLite supports limited concurrency but not multiple writers from different processes.

**Disk full.** The SQLite journal file could not be written, leaving the database in an inconsistent state.

**Previous run crashed.** Files marked `InProgress` were being processed when the agent terminated unexpectedly. They are now stuck because no batch is actively managing them.

### Solution

**For corrupted databases:**

1. **Attempt recovery with the SQLite CLI:**
   ```bash
   sqlite3 migration-state.db ".recover" | sqlite3 migration-state-recovered.db
   ```
   If recovery succeeds, replace the original:
   ```bash
   mv migration-state.db migration-state-corrupt-backup.db
   mv migration-state-recovered.db migration-state.db
   ```

2. **If recovery fails, reset the database entirely:**
   ```bash
   rm migration-state.db
   # The agent will recreate it and re-import from the CSV on next run
   # All progress will be lost -- previously succeeded files will be re-processed
   ```

3. **Partial reset -- keep successes:**
   If you have a backup or can identify which files already succeeded (e.g., from Datadog logs or previous reports), you can recreate the database and manually mark files:
   ```bash
   rm migration-state.db
   # Start the agent to recreate the database
   dotnet run --project src/FtpAgent/FtpAgent.csproj -- --dry-run
   # Ctrl+C after it loads
   # Mark known successes
   sqlite3 migration-state.db "UPDATE file_entries SET Status = 2 WHERE Id IN ('file-0001', 'file-0002', ...);"
   ```

**For stuck InProgress files:**

```bash
# Reset all InProgress files back to Pending
sqlite3 migration-state.db "UPDATE file_entries SET Status = 0 WHERE Status = 1;"

# Or reset to RetryPending if they were mid-retry
sqlite3 migration-state.db "UPDATE file_entries SET Status = 4 WHERE Status = 1 AND RetryCount > 0;"
```

**For manually marking specific files:**

```bash
# Mark a file as succeeded (skip further processing)
sqlite3 migration-state.db "UPDATE file_entries SET Status = 2 WHERE Id = 'file-0321';"

# Mark a file as failed (stop retrying)
sqlite3 migration-state.db "UPDATE file_entries SET Status = 3 WHERE Id = 'file-0500';"

# Reset a file to pending (reprocess from scratch)
sqlite3 migration-state.db "UPDATE file_entries SET Status = 0, RetryCount = 0, LastError = '' WHERE Id = 'file-0500';"
```

### Prevention

- Always stop the agent gracefully with `Ctrl+C` (which triggers `CancellationToken` cancellation). Avoid `kill -9`.
- Never run two instances of the agent with the same `StateDatabasePath`.
- Back up the database periodically during long migration runs:
  ```bash
  cp migration-state.db migration-state-backup-$(date +%Y%m%d-%H%M).db
  ```
- Add a startup check in the agent that detects and recovers stuck `InProgress` files automatically.
- Ensure the disk where the database is stored has adequate free space.

---

## 7. Git Push Rejected

### Symptom

The agent fails when trying to push config changes:

```
[2026-02-07 08:00:30 ERR] GitManager: push failed
error: failed to push some refs to 'origin/main'
hint: Updates were rejected because the remote contains work that you do not have locally.
```

Or:

```
[2026-02-07 08:00:30 ERR] GitManager: push failed
remote: error: GH006: Protected branch update failed for refs/heads/main.
remote: error: Required status checks are expected.
```

### Likely Cause

**Merge conflict.** Someone else pushed to the same branch while the agent was preparing its commit. The remote has commits the agent does not have locally.

**Branch protection rules.** The target branch requires pull requests, status checks, or reviews. Direct pushes are blocked.

**Authentication expired.** The `gh` CLI or git credential manager token has expired.

**Force push required.** A previous force push or rebase by someone else has diverged the history.

### Solution

**For merge conflicts:**

1. Pull and rebase:
   ```bash
   cd /repos/file-ingestion-app
   git pull --rebase origin main
   ```

2. If there are conflicts in config files, resolve them (the agent's version is almost always correct since config files do not overlap between migration batches).

3. Push again:
   ```bash
   git push origin main
   ```

4. Restart the agent. It will detect the files are still `InProgress` and continue from the build step.

**For branch protection:**

1. If the repo requires PRs, modify the agent to push to a feature branch and create a PR:
   ```json
   {
     "GitHub": {
       "BaseBranch": "main",
       "UsePullRequests": true
     }
   }
   ```

2. Alternatively, add an exception for the agent's service account in the branch protection rules:
   ```
   GitHub -> Settings -> Branches -> main -> Branch protection rules ->
   "Allow specified actors to bypass required pull requests" -> Add the agent's GitHub user
   ```

**For authentication:**

1. Re-authenticate:
   ```bash
   gh auth login
   gh auth status
   ```

2. Verify git credentials:
   ```bash
   git config credential.helper
   git credential fill <<< "protocol=https
   host=github.com
   "
   ```

### Prevention

- Coordinate with the team: during migration runs, avoid making manual changes to the config directory in the target repo.
- If multiple people need to push to the same branch, use a dedicated migration branch and merge to main periodically.
- Set up a long-lived Personal Access Token or GitHub App token for the agent that does not expire during a migration run.
- Run `git pull --rebase` before each commit in the `GitManager` to stay current with remote.

---

## 8. Copilot CLI Not Responding

### Symptom

The agent hangs or times out when calling the Copilot CLI for config translation or error diagnosis:

```
[2026-02-07 08:00:05 ERR] ConfigTranslator: Copilot CLI timed out after 120s for file-0321
```

Or returns an error:

```
[2026-02-07 08:00:05 ERR] ConfigTranslator: Copilot CLI error: "You are not authorized to use GitHub Copilot"
```

Or:

```
[2026-02-07 08:00:05 ERR] ConfigTranslator: Copilot CLI error: "Rate limit exceeded. Please try again in 60 seconds."
```

### Likely Cause

**Authentication expired.** The `gh` CLI session or Copilot license has expired.

**Rate limiting.** Too many requests in a short period. The agent processes files sequentially, but rapid retries or large batches can trigger rate limits.

**Model unavailable.** The specified model (`claude-opus-4-5-20250514`) may be temporarily unavailable or renamed.

**Network issue.** The machine cannot reach GitHub's API or the Copilot service.

**Prompt too large.** The rendered prompt exceeds the model's context window, causing the CLI to hang or return an error.

### Solution

1. **Re-authenticate:**
   ```bash
   gh auth login
   gh auth status
   gh copilot --help  # Verify Copilot is available
   ```

2. **Check rate limits.** If rate-limited, increase the delay between Copilot calls. The agent can be configured to add a pause:
   ```json
   {
     "Copilot": {
       "TimeoutSeconds": 180,
       "DelayBetweenCallsMs": 2000
     }
   }
   ```

3. **Verify the model is available:**
   ```bash
   gh copilot suggest "Hello" --model claude-opus-4-5-20250514
   ```
   If the model name is invalid, check the Copilot documentation for current model identifiers and update `appsettings.json`.

4. **Check network connectivity:**
   ```bash
   curl -s https://api.github.com/zen
   ```
   If this fails, the machine has network issues.

5. **Reduce prompt size.** If the legacy config blob is very large, the rendered prompt may exceed token limits. Check the prompt size:
   ```bash
   wc -c prompts/config-translation.md
   # If over 10,000 characters, consider trimming examples or splitting
   ```

6. **Increase the timeout** for legitimately slow responses:
   ```json
   {
     "Copilot": {
       "TimeoutSeconds": 300
     }
   }
   ```

### Prevention

- Use a service account with a dedicated Copilot license for the agent.
- Set reasonable batch sizes to avoid hitting rate limits.
- Add retry logic with exponential backoff for transient Copilot failures (the `DiagnosticEngine` and `ConfigTranslator` should implement this).
- Monitor the `gh auth status` output periodically; set up a cron job to alert if auth expires.
- Keep prompt templates concise. Aim for under 2000 words including examples.

---

## 9. Files Download but Wrong Content

### Symptom

Datadog shows successful file downloads, but downstream consumers report that the file content is wrong. Examples:

- File is downloaded but contains binary garbage (encoding issue)
- File is downloaded but is still PGP-encrypted (decryption did not run)
- File is the right format but from the wrong directory (path issue)
- File is yesterday's file, not today's (pattern matching issue)

The agent marks these files as "success" because the download itself completed without errors.

### Likely Cause

**Config path issue.** The `remote_path` or `file_pattern` is technically valid but points to the wrong directory or matches the wrong files on the SFTP server.

**PGP decryption not configured.** The legacy config mentions PGP but the translation did not include the `pgp_decryption` section, so the file is downloaded but not decrypted.

**Encoding mismatch.** The file needs to be interpreted as a specific encoding (e.g., ISO-8859-1) but the application defaults to UTF-8.

**Date pattern mismatch.** The `file_pattern` uses a date format like `YYYYMMDD` but the server uses `MMDDYYYY` or day-of-year format (`YYYYDDD`).

**Multiple files match the pattern.** The glob pattern is too broad and matches both the current file and historical files.

### Solution

1. **Compare the downloaded file against a known-good sample.** Check the S3 bucket where the file was uploaded and compare it to a file downloaded manually from the same SFTP server.

2. **Verify the PGP configuration.** If the file should be decrypted:
   ```bash
   # Check if the config has a pgp_decryption section
   cat /repos/file-ingestion-app/configs/problem-file.yaml | grep -A 3 pgp_decryption
   ```
   If missing, the translation prompt needs a better example for this type of config.

3. **Check the file pattern on the actual server.** SSH into the SFTP server (or ask the file provider) and list the directory:
   ```bash
   sftp user@host
   ls /outbound/reports/
   ```
   Compare the actual filenames against the configured `file_pattern`.

4. **Fix the config manually** and mark the file for retry:
   ```bash
   # Edit the config
   vim /repos/file-ingestion-app/configs/problem-file.yaml

   # Reset the file in the state store
   sqlite3 migration-state.db "UPDATE file_entries SET Status = 4, RetryCount = 0 WHERE Name = 'problem-file';"
   ```

5. **Add the failure pattern to the diagnosis prompt** so the LLM can catch it in the future.

### Prevention

- Add a content validation step after download: check file size (>0 bytes), file extension matches expectation, and first few bytes are not PGP header if decryption should have occurred.
- Add the file pattern ambiguity issue to the translation prompt with an explicit rule:
  ```markdown
  - If the legacy file pattern includes a date component, verify the date
    format matches the server's actual naming convention
  - Prefer specific patterns over broad ones (ACME_DAILY_20*.csv is better
    than ACME_*.csv)
  ```
- Consider adding a "smoke test" step that verifies the downloaded file's content type before marking the migration as successful.

---

## 10. Agent Keeps Retrying the Same Error

### Symptom

A file fails, gets diagnosed, gets a suggested fix, retries, and fails again with the same error. This repeats until `MaxRetriesPerFile` is reached:

```
[2026-02-07 08:17:13 INF] DiagnosticEngine: root cause = "SFTP host key verification failed"
[2026-02-07 08:17:13 INF] Applying fix: connection.strict_host_key_checking false -> true
# ... retry deploys, fails again ...
[2026-02-07 08:33:02 ERR] file-0329: FAILED (attempt 2/3) - "SFTP host key verification failed"
[2026-02-07 08:33:03 INF] DiagnosticEngine: root cause = "SFTP host key verification failed"
[2026-02-07 08:33:03 INF] Applying fix: connection.strict_host_key_checking true -> false
# ... oscillates back and forth ...
```

### Likely Cause

**The issue is not fixable via config changes.** The root cause is environmental (e.g., missing host key in `known_hosts`, expired SSL certificate, firewall rule, server-side permission change) and no amount of YAML changes will fix it.

**The LLM oscillates between fixes.** Without memory of previous attempts, the LLM may suggest undoing the previous fix, creating an infinite loop.

**The diagnosis prompt does not include the retry history.** The LLM does not know that the same fix was already tried and failed.

**Max retries is set too high.** Each retry wastes a build/deploy cycle (10+ minutes) on a file that will never succeed without manual intervention.

### Solution

1. **Check the retry history** in the state store:
   ```bash
   sqlite3 migration-state.db "SELECT Id, Name, RetryCount, LastError FROM file_entries WHERE Status = 4 AND RetryCount >= 2;"
   ```

2. **Manually investigate the root cause.** For environmental issues, the fix is outside the agent's scope:
   - SSH host key: `ssh-keyscan sftp.host.com >> /app/known_hosts`
   - Expired certificate: Contact the SFTP server operator
   - Firewall: Contact network team
   - Server-side permissions: Contact the file provider

3. **Mark the file as permanently failed** to stop retries:
   ```bash
   sqlite3 migration-state.db "UPDATE file_entries SET Status = 3, LastError = 'Manual: requires host key in known_hosts' WHERE Id = 'file-0329';"
   ```

4. **Improve the diagnosis prompt** to include retry history. The `DiagnosticEngine` should pass the previous diagnosis and fix attempt to the LLM:
   ```markdown
   ## Previous Attempts
   Attempt 1: Changed strict_host_key_checking to false. Result: same error.
   Attempt 2: Changed strict_host_key_checking to true. Result: same error.

   The config changes are not fixing this issue. Consider whether this is an
   environmental problem (server-side, network, or credential issue) rather
   than a configuration problem.
   ```

5. **Reduce MaxRetriesPerFile** if many files are hitting this pattern:
   ```json
   {
     "Agent": {
       "MaxRetriesPerFile": 2
     }
   }
   ```

### Prevention

- Include the full retry history in the diagnosis prompt so the LLM does not repeat failed fixes.
- Add a "same error detected" check: if the error message on retry is identical to the previous error, skip diagnosis and immediately mark as failed with a note that manual intervention is needed.
- Categorize errors into "config-fixable" and "environmental" in the diagnosis prompt. Environmental errors should be immediately marked as non-recoverable.
- Set `MaxRetriesPerFile` to 2-3. More than 3 retries rarely succeeds if the first fix attempt did not work.
- Generate a report of all files that hit max retries, grouped by error type, so an operator can address them in bulk (e.g., "15 files need host keys added to known_hosts").

---

## Quick Reference: Common Commands

### State Store Queries

```bash
# Count files by status
sqlite3 migration-state.db "SELECT
  CASE Status
    WHEN 0 THEN 'Pending'
    WHEN 1 THEN 'InProgress'
    WHEN 2 THEN 'Success'
    WHEN 3 THEN 'Failed'
    WHEN 4 THEN 'RetryPending'
  END as StatusName,
  COUNT(*)
FROM file_entries GROUP BY Status;"

# Find files stuck in InProgress
sqlite3 migration-state.db "SELECT Id, Name, UpdatedAt FROM file_entries WHERE Status = 1 ORDER BY UpdatedAt;"

# List all failed files with their errors
sqlite3 migration-state.db "SELECT Id, Name, RetryCount, LastError FROM file_entries WHERE Status = 3;"

# Reset a specific file
sqlite3 migration-state.db "UPDATE file_entries SET Status = 0, RetryCount = 0, LastError = '' WHERE Id = 'file-XXXX';"

# Reset all stuck InProgress files
sqlite3 migration-state.db "UPDATE file_entries SET Status = 0 WHERE Status = 1;"

# Mark a file as permanently succeeded (skip processing)
sqlite3 migration-state.db "UPDATE file_entries SET Status = 2 WHERE Id = 'file-XXXX';"
```

### External Service Checks

```bash
# GitHub Actions
gh run list --repo owner/repo --branch main --limit 5
gh run view RUN_ID --repo owner/repo --log

# GitHub auth
gh auth status

# Datadog API
curl -s "https://api.datadoghq.com/api/v1/validate" \
  -H "DD-API-KEY: $DD_API_KEY"

# Octopus Deploy
curl -s "$OCTOPUS_URL/api/users/me" \
  -H "X-Octopus-ApiKey: $OCTOPUS_API_KEY"

# Git remote
git -C /repos/file-ingestion-app remote -v
git -C /repos/file-ingestion-app log --oneline -5
```

### Agent Operations

```bash
# Start in dry-run mode
dotnet run --project src/FtpAgent/FtpAgent.csproj -- --dry-run

# Start with a small batch for testing
FTPAGENT_Agent__BatchSize=2 dotnet run --project src/FtpAgent/FtpAgent.csproj -- --dry-run

# Start with verbose logging
FTPAGENT_Logging__LogLevel__Default=Debug dotnet run --project src/FtpAgent/FtpAgent.csproj -- --dry-run

# Back up state before a run
cp migration-state.db migration-state-backup-$(date +%Y%m%d-%H%M).db
```

---

## Getting Further Help

If a problem is not covered in this guide:

1. Check `docs/WALKTHROUGH.md` to understand where in the pipeline the failure occurs.
2. Check `ARCHITECTURE.md` for design details about the specific component.
3. Search Datadog logs for the file ingestion application directly to see raw error output.
4. Open a GitHub issue with the full error log, the file's legacy config, the translated config, and the Datadog log output.
