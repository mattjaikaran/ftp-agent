# FTP Agent - Setup Guide

Complete setup instructions for running the FTP Agent on a Linux VM. This agent automates the migration of ~1400 file ingestion configurations from a legacy system to a new Docker-based app running in EKS. It uses Claude Opus 4.5 (via GitHub Copilot CLI), GitHub Actions, Octopus Deploy, and Datadog.

**Target environment:** Linux VM (Ubuntu/Debian or RHEL/CentOS), .NET 8, running as a console application.

---

## Table of Contents

1. [Linux VM Setup](#1-linux-vm-setup)
2. [GitHub Authentication](#2-github-authentication)
3. [Datadog API Setup](#3-datadog-api-setup)
4. [Octopus Deploy Setup](#4-octopus-deploy-setup)
5. [Configuration](#5-configuration)
6. [Preparing the Legacy Config File](#6-preparing-the-legacy-config-file)
7. [First Run](#7-first-run)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Linux VM Setup

### 1.1 Install .NET 8 SDK

The agent is a .NET 8 console application. You need the full SDK (not just the runtime) to build and run from source.

#### Ubuntu / Debian

```bash
# Add the Microsoft package repository
wget https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
sudo dpkg -i packages-microsoft-prod.deb
rm packages-microsoft-prod.deb

# Install the .NET 8 SDK
sudo apt-get update
sudo apt-get install -y dotnet-sdk-8.0
```

If `lsb_release` is not available, replace `$(lsb_release -rs)` with your Ubuntu version number (e.g., `22.04` or `24.04`).

#### RHEL / CentOS / Fedora

```bash
# Add the Microsoft package repository
sudo rpm -Uvh https://packages.microsoft.com/config/rhel/$(rpm -E %rhel)/packages-microsoft-prod.rpm

# Install the .NET 8 SDK
sudo dnf install -y dotnet-sdk-8.0
```

On older CentOS versions that use `yum` instead of `dnf`:

```bash
sudo yum install -y dotnet-sdk-8.0
```

#### Verify Installation

```bash
dotnet --version
```

Expected output: `8.0.xxx` (any 8.0.x patch version is fine).

```bash
dotnet --list-sdks
```

You should see at least one entry starting with `8.0`.

### 1.2 Install Git

#### Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install -y git
```

#### RHEL / CentOS

```bash
sudo dnf install -y git
```

#### Verify

```bash
git --version
```

Expected: `git version 2.x.x` (any reasonably recent version works).

### 1.3 Install GitHub CLI (`gh`)

The agent uses `gh` to interact with GitHub Actions workflows and to invoke GitHub Copilot CLI.

#### Ubuntu / Debian

```bash
# Add the GitHub CLI repository
(type -p wget >/dev/null || sudo apt install wget) \
  && sudo mkdir -p -m 755 /etc/apt/keyrings \
  && wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
  && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
  && sudo apt update \
  && sudo apt install gh -y
```

#### RHEL / CentOS

```bash
sudo dnf install 'dnf-command(config-manager)' -y
sudo dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo
sudo dnf install gh -y
```

#### Verify

```bash
gh --version
```

Expected: `gh version 2.x.x` or later.

### 1.4 Install GitHub Copilot CLI Extension

The agent uses `gh copilot` to invoke Claude Opus 4.5 for config translation and error diagnosis.

```bash
gh extension install github/gh-copilot
```

Verify it installed:

```bash
gh copilot --version
```

If you get a "not found" error, make sure `gh` is authenticated first (see Section 2), then retry the install.

### 1.5 Install Additional Dependencies

SQLite is used for state persistence. It is typically already installed on most Linux distributions, but just in case:

#### Ubuntu / Debian

```bash
sudo apt-get install -y sqlite3 libsqlite3-dev
```

#### RHEL / CentOS

```bash
sudo dnf install -y sqlite sqlite-devel
```

### 1.6 Verify All Tools

Run this verification block to confirm everything is installed correctly:

```bash
echo "=== .NET SDK ==="
dotnet --version

echo ""
echo "=== Git ==="
git --version

echo ""
echo "=== GitHub CLI ==="
gh --version

echo ""
echo "=== GitHub Copilot Extension ==="
gh copilot --version

echo ""
echo "=== SQLite ==="
sqlite3 --version

echo ""
echo "All tools verified."
```

Every command above should produce version output without errors. If any command fails, revisit the corresponding installation step.

---

## 2. GitHub Authentication

The agent needs GitHub access for two purposes:
- **Git push**: Pushing config changes to the target repository (the file ingestion app repo).
- **GitHub API**: Monitoring GitHub Actions workflow runs for build status.

### 2.1 Create a Personal Access Token (PAT)

1. Go to [https://github.com/settings/tokens](https://github.com/settings/tokens).
2. Click **"Generate new token"** and choose **"Generate new token (classic)"**.
3. Give it a descriptive name, e.g., `ftp-agent-linux-vm`.
4. Set an expiration (90 days is a reasonable starting point; you can rotate it later).
5. Select the following scopes:

| Scope | Why It Is Needed |
|---|---|
| `repo` | Full control of private repositories. Needed to push config changes and read workflow status. |
| `workflow` | Allows the agent to trigger and read GitHub Actions workflow runs. |
| `read:org` | Read-only access to organization membership. Needed if the target repo is in an org. |

6. Click **"Generate token"**.
7. **Copy the token immediately.** You will not be able to see it again. Store it securely (e.g., a password manager or a secrets vault).

> **Fine-grained tokens alternative:** If your organization uses fine-grained personal access tokens, you need: Repository access to the target repo, with permissions for Contents (Read and Write), Actions (Read), and Metadata (Read).

### 2.2 Authenticate `gh` CLI

On the Linux VM, run:

```bash
gh auth login
```

When prompted:
- **Where do you use GitHub?** Select `GitHub.com` (or your GitHub Enterprise Server URL if applicable).
- **Preferred protocol for Git operations?** Select `SSH` (recommended) or `HTTPS`.
- **Authenticate GitHub CLI?** Select `Paste an authentication token`.
- Paste the PAT you created in step 2.1.

Verify authentication:

```bash
gh auth status
```

Expected output should show your username and the token scopes. Example:

```
github.com
  ✓ Logged in to github.com account your-username (keyring)
  - Active account: true
  - Git operations protocol: ssh
  - Token: ghp_****
  - Token scopes: 'read:org', 'repo', 'workflow'
```

Confirm all three scopes (`repo`, `workflow`, `read:org`) are listed.

### 2.3 Set Up SSH Keys for Git Push

The agent uses `git push` via SSH. If the VM does not already have SSH keys configured for GitHub:

#### Generate a new SSH key pair

```bash
ssh-keygen -t ed25519 -C "ftp-agent@your-vm-hostname" -f ~/.ssh/id_ed25519 -N ""
```

The `-N ""` flag creates the key without a passphrase. This is necessary for the agent to push without interactive prompts. If your security policy requires a passphrase, you will need to configure `ssh-agent` to hold the key in memory.

#### Add the public key to GitHub

Display the public key:

```bash
cat ~/.ssh/id_ed25519.pub
```

Copy the entire output. Then:

1. Go to [https://github.com/settings/keys](https://github.com/settings/keys).
2. Click **"New SSH key"**.
3. Title: `ftp-agent-linux-vm` (or similar).
4. Key type: **Authentication key**.
5. Paste the public key.
6. Click **"Add SSH key"**.

#### Test SSH connectivity

```bash
ssh -T git@github.com
```

Expected output:

```
Hi your-username! You've successfully authenticated, but GitHub does not provide shell access.
```

If you see `Permission denied (publickey)`, check that:
- The key file permissions are correct: `chmod 600 ~/.ssh/id_ed25519` and `chmod 644 ~/.ssh/id_ed25519.pub`.
- The public key is added to the correct GitHub account.
- Your `~/.ssh/config` is not overriding the identity file.

#### Configure SSH to use the correct key (optional)

If you have multiple SSH keys, add this to `~/.ssh/config`:

```
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

### 2.4 Copilot CLI Authentication

After `gh auth login` succeeds, Copilot CLI should be ready to use. Test it:

```bash
gh copilot suggest "echo hello world"
```

If you get an error about Copilot access:
- Confirm your GitHub account (or organization) has a **GitHub Copilot subscription** (Individual, Business, or Enterprise).
- If you are in an organization, ask an admin to enable Copilot for your account.
- Try re-authenticating: `gh auth refresh -s copilot`.

### 2.5 Configure Git Identity

The agent creates commits, so git needs a name and email:

```bash
git config --global user.name "FTP Migration Agent"
git config --global user.email "ftp-agent@your-org.com"
```

Replace the email with whatever your team uses for automated commits.

---

## 3. Datadog API Setup

The agent queries Datadog Logs API to determine whether migrated files are downloading successfully after deployment.

### 3.1 Locate Your Datadog API Key

1. Log in to your Datadog account at [https://app.datadoghq.com](https://app.datadoghq.com) (or your regional site).
2. Navigate to **Organization Settings** > **API Keys**.
   - Direct URL: `https://app.datadoghq.com/organization-settings/api-keys`
3. You should see existing API keys. Copy one, or create a new one:
   - Click **"+ New Key"**.
   - Name it `ftp-agent`.
   - Copy the key value.

> **What is an API Key?** The API key identifies your organization. It is used for all Datadog API calls. Every member of your Datadog org can see the same API keys.

### 3.2 Create an Application Key

Application keys are per-user and provide additional authorization for reading data (like logs).

1. Navigate to **Organization Settings** > **Application Keys**.
   - Direct URL: `https://app.datadoghq.com/organization-settings/application-keys`
2. Click **"+ New Key"**.
3. Name it `ftp-agent`.
4. Copy the key value immediately. You will not be able to see the full value again.

> **What is an Application Key?** The application key is tied to your user account and authorizes the agent to read data on your behalf. It is separate from the API key. Both are required for Logs API queries.

### 3.3 Identify Your Datadog Site

Datadog has multiple regional sites. The agent needs to know which one you use so it can call the correct API endpoint.

| If your Datadog URL starts with... | Your Datadog site value is | API base URL |
|---|---|---|
| `app.datadoghq.com` | `datadoghq.com` | `https://api.datadoghq.com` |
| `app.datadoghq.eu` | `datadoghq.eu` | `https://api.datadoghq.eu` |
| `app.us3.datadoghq.com` | `us3.datadoghq.com` | `https://api.us3.datadoghq.com` |
| `app.us5.datadoghq.com` | `us5.datadoghq.com` | `https://api.us5.datadoghq.com` |
| `app.ap1.datadoghq.com` | `ap1.datadoghq.com` | `https://api.ap1.datadoghq.com` |
| `app.ddog-gov.com` | `ddog-gov.com` | `https://api.ddog-gov.com` |

The **API base URL** is what goes in the `Datadog.ApiUrl` configuration field.

### 3.4 Test API Access

Replace the placeholders with your actual keys and API base URL:

```bash
DD_API_KEY="your-api-key-here"
DD_APP_KEY="your-application-key-here"
DD_API_URL="https://api.datadoghq.com"

curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" \
  "${DD_API_URL}/api/v1/validate" \
  -H "DD-API-KEY: ${DD_API_KEY}"
```

Expected: `HTTP Status: 200`. If you get `403`, your API key is wrong or revoked.

Now test log access (requires both keys):

```bash
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" \
  "${DD_API_URL}/api/v2/logs/events/search" \
  -H "DD-API-KEY: ${DD_API_KEY}" \
  -H "DD-APPLICATION-KEY: ${DD_APP_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "query": "service:your-service-name",
      "from": "now-15m",
      "to": "now"
    },
    "page": {
      "limit": 5
    }
  }'
```

Expected: `HTTP Status: 200`. If you get `403`, your application key may not have the right permissions or may be associated with a restricted role.

### 3.5 Find Your Service Name and Log Patterns

You will need three pieces of information for the agent configuration:

1. **Service name**: The `service` tag attached to logs from the file ingestion app in Datadog. Find this by going to **Logs > Search** in Datadog and looking at existing log entries from the app. It is typically visible in the log facets sidebar under `Service`.

2. **Success log pattern**: A search query that matches log lines indicating a file was downloaded successfully. For example: `"Download completed successfully"` or `status:ok source:file-ingestion`.

3. **Failure log pattern**: A search query that matches log lines indicating a failure. For example: `"Download failed"` or `status:error source:file-ingestion`.

Consult with the team that runs the file ingestion app to determine the exact patterns.

---

## 4. Octopus Deploy Setup

The agent triggers Octopus Deploy to deploy new builds of the file ingestion app after GitHub Actions produces a new Docker image.

### 4.1 Find the Octopus Server URL

This is the base URL of your Octopus Deploy instance. It typically looks like:

- Self-hosted: `https://octopus.your-company.com`
- Octopus Cloud: `https://your-instance.octopus.app`

Ask your DevOps team if you are unsure.

### 4.2 Create an API Key in Octopus

1. Log in to Octopus Deploy.
2. Click your profile avatar in the top-right corner, then click **"Profile"**.
3. Navigate to the **"API Keys"** tab.
4. Click **"New API Key"**.
5. Enter a purpose: `ftp-agent automation`.
6. Optionally set an expiry date.
7. Click **"Generate New"**.
8. **Copy the API key immediately.** It starts with `API-` and will only be shown once.

> **Permissions note**: The API key inherits the permissions of the user who created it. Ensure the user has at least these permissions:
> - **DeploymentCreate** on the target project and environment.
> - **ReleaseView** to check release/deployment status.
> - **TaskView** to monitor deployment tasks.
>
> Ask your Octopus admin to create a service account with limited permissions if you do not want to use your personal account.

### 4.3 Find the Project Name and Environment Name

1. In Octopus, navigate to **Projects** in the top menu.
2. Find the project for the file ingestion app. The project name as displayed in Octopus is what you use for `OctopusDeploy.ProjectName`.
3. Navigate to the project, then go to the **"Deployments"** section (or **"Infrastructure" > "Environments"**).
4. Note the environment name you want the agent to deploy to (e.g., `Development`, `Staging`). This is what you use for `OctopusDeploy.EnvironmentName`.

### 4.4 Find the Space ID (if applicable)

If your Octopus instance uses Spaces (most do):

1. Navigate to the Space selector (top-left dropdown in Octopus).
2. The default space is `Spaces-1`. If your project is in a different space, you can find the Space ID in the URL when you are inside that space: `https://octopus.your-company.com/app#/Spaces-42/...`
3. Use this value for `OctopusDeploy.SpaceId`.

### 4.5 Test API Access

```bash
OCTOPUS_URL="https://octopus.your-company.com"
OCTOPUS_API_KEY="API-XXXXXXXXXXXXXXXXXXXXXXXXXXXX"

curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" \
  "${OCTOPUS_URL}/api" \
  -H "X-Octopus-ApiKey: ${OCTOPUS_API_KEY}"
```

Expected: `HTTP Status: 200`. If you get a JSON response with the Octopus API root, the connection is working.

Test that you can access the project:

```bash
curl -s "${OCTOPUS_URL}/api/Spaces-1/projects/all" \
  -H "X-Octopus-ApiKey: ${OCTOPUS_API_KEY}" | python3 -m json.tool | head -30
```

You should see a JSON array of projects. Find your project in the list.

### 4.6 Using StubDeploymentClient (For Initial Development)

If you do not have Octopus Deploy access yet, the agent can run with a stub deployment client that simulates deployments. This is enabled automatically when you run with `--dry-run`:

```bash
dotnet run --project src/FtpAgent -- --dry-run
```

The `StubDeploymentClient` logs what it would deploy without making real API calls. You can fully test the config-translation, git-commit, and build-monitoring pipeline without Octopus.

---

## 5. Configuration

### 5.1 Create Your Local Configuration File

The project uses two configuration files:
- `appsettings.json` -- Checked into source control. Contains default values and non-sensitive settings.
- `appsettings.Development.json` -- **NOT checked into source control.** Contains your API keys and environment-specific values.

Create your local config:

```bash
cd /path/to/ftp-agent
cp config/appsettings.json config/appsettings.Development.json
```

> **Important:** `appsettings.Development.json` should already be listed in `.gitignore`. Verify this:
> ```bash
> grep -q "appsettings.Development.json" .gitignore && echo "OK: File is in .gitignore" || echo "WARNING: Add appsettings.Development.json to .gitignore!"
> ```
> If it is not in `.gitignore`, add it immediately before proceeding:
> ```bash
> echo "config/appsettings.Development.json" >> .gitignore
> echo "appsettings.Development.json" >> .gitignore
> ```

### 5.2 Fill in Configuration Values

Edit `config/appsettings.Development.json` with your actual values. Here is the complete file with explanations for each field:

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
    "RepoOwner": "your-org-or-username",
    "RepoName": "file-ingestion-app",
    "TargetBranch": "main",
    "WorkflowFileName": "build.yml"
  },
  "OctopusDeploy": {
    "ServerUrl": "https://octopus.your-company.com",
    "ApiKey": "API-XXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "ProjectName": "File Ingestion App",
    "EnvironmentName": "Development",
    "SpaceId": "Spaces-1"
  },
  "Datadog": {
    "ApiUrl": "https://api.datadoghq.com",
    "ApiKey": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "AppKey": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "ServiceName": "file-ingestion",
    "Environment": "development"
  },
  "Copilot": {
    "CliPath": "gh",
    "Model": "claude-opus-4-5-20250514",
    "TimeoutSeconds": 120,
    "ConfigTranslationPromptPath": "prompts/config-translation.md",
    "ErrorDiagnosisPromptPath": "prompts/error-diagnosis.md"
  }
}
```

#### Field-by-Field Reference

**Agent section** -- Controls the autonomous loop behavior.

| Field | Description | Recommended Starting Value |
|---|---|---|
| `BatchSize` | Number of legacy files to process in each batch before committing, building, deploying, and checking. | `5` for initial testing, `20` for production runs. |
| `MaxRetriesPerFile` | How many times to attempt fixing a single file before marking it as permanently failed. | `3` |
| `DeployWaitTimeoutMinutes` | Maximum time to wait for a GitHub Actions build or Octopus deployment to complete. | `15` |
| `DatadogCheckDelayMinutes` | How long to wait after deployment before querying Datadog for logs. Gives the app time to attempt file downloads. | `5` |
| `LogQueryWindowMinutes` | Time window to search in Datadog logs when checking file download status. | `30` |

**GitHub section** -- Identifies the target repository (the file ingestion app, not this agent repo).

| Field | Description | Example |
|---|---|---|
| `RepoOwner` | GitHub organization or username that owns the target repo. | `your-org` |
| `RepoName` | Name of the target repository. | `file-ingestion-app` |
| `TargetBranch` | Branch to push config changes to. | `main` |
| `WorkflowFileName` | The GitHub Actions workflow file that builds the Docker image. Must match a file under `.github/workflows/` in the target repo. | `build.yml` |

**OctopusDeploy section** -- Connection details for the deployment server.

| Field | Description | Example |
|---|---|---|
| `ServerUrl` | Full URL of your Octopus Deploy instance. Include the protocol, no trailing slash. | `https://octopus.your-company.com` |
| `ApiKey` | Octopus API key (starts with `API-`). Created in Section 4.2. | `API-XXXXXXXXXXXXXXXXXXXXXXXXXXXX` |
| `ProjectName` | Exact project name as shown in Octopus. Case-sensitive. | `File Ingestion App` |
| `EnvironmentName` | Exact environment name as shown in Octopus. Case-sensitive. | `Development` |
| `SpaceId` | Octopus Space ID. Default space is `Spaces-1`. | `Spaces-1` |

**Datadog section** -- Connection details for log monitoring.

| Field | Description | Example |
|---|---|---|
| `ApiUrl` | Datadog API base URL. Depends on your Datadog site (see Section 3.3). | `https://api.datadoghq.com` |
| `ApiKey` | Datadog API key (32 hex characters). Created in Section 3.1. | `abcdef1234567890abcdef1234567890` |
| `AppKey` | Datadog Application key (40 hex characters). Created in Section 3.2. | `abcdef1234567890abcdef1234567890abcdef12` |
| `ServiceName` | The `service` tag in Datadog logs for the file ingestion app. | `file-ingestion` |
| `Environment` | The `env` tag in Datadog logs for the target environment. | `development` |

**Copilot section** -- Controls how the agent invokes Claude Opus 4.5.

| Field | Description | Example |
|---|---|---|
| `CliPath` | Path to the `gh` CLI binary. Use `gh` if it is on your PATH, or provide an absolute path. | `gh` or `/usr/bin/gh` |
| `Model` | The model identifier to use via Copilot. | `claude-opus-4-5-20250514` |
| `TimeoutSeconds` | Maximum time to wait for a Copilot response. Increase if you experience timeouts on complex translations. | `120` |
| `ConfigTranslationPromptPath` | Path to the prompt template for config translation, relative to project root. | `prompts/config-translation.md` |
| `ErrorDiagnosisPromptPath` | Path to the prompt template for error diagnosis, relative to project root. | `prompts/error-diagnosis.md` |

### 5.3 Environment Variables Alternative

For production deployments or CI/CD, you can set configuration values via environment variables instead of (or in addition to) the JSON file. The agent reads environment variables prefixed with `FTPAGENT_`.

The naming convention uses double underscores (`__`) to represent JSON nesting:

```bash
# GitHub
export FTPAGENT_GitHub__RepoOwner="your-org"
export FTPAGENT_GitHub__RepoName="file-ingestion-app"
export FTPAGENT_GitHub__TargetBranch="main"
export FTPAGENT_GitHub__WorkflowFileName="build.yml"

# Octopus Deploy
export FTPAGENT_OctopusDeploy__ServerUrl="https://octopus.your-company.com"
export FTPAGENT_OctopusDeploy__ApiKey="API-XXXXXXXXXXXXXXXXXXXXXXXXXXXX"
export FTPAGENT_OctopusDeploy__ProjectName="File Ingestion App"
export FTPAGENT_OctopusDeploy__EnvironmentName="Development"
export FTPAGENT_OctopusDeploy__SpaceId="Spaces-1"

# Datadog
export FTPAGENT_Datadog__ApiUrl="https://api.datadoghq.com"
export FTPAGENT_Datadog__ApiKey="your-datadog-api-key"
export FTPAGENT_Datadog__AppKey="your-datadog-app-key"
export FTPAGENT_Datadog__ServiceName="file-ingestion"
export FTPAGENT_Datadog__Environment="development"

# Copilot
export FTPAGENT_Copilot__Model="claude-opus-4-5-20250514"
export FTPAGENT_Copilot__TimeoutSeconds="120"

# Agent behavior
export FTPAGENT_Agent__BatchSize="5"
export FTPAGENT_Agent__MaxRetriesPerFile="3"
```

Environment variables take precedence over values in `appsettings.json` and `appsettings.Development.json`. This is useful for injecting secrets without writing them to disk.

> **Tip for systemd services:** If you run the agent as a systemd service, put these variables in the service unit file under `[Service]` using `Environment=` directives, or use `EnvironmentFile=` to point to a secured file.

### 5.4 Security Reminder

**Never commit secrets to source control.** The following files and patterns should be in `.gitignore`:

```
appsettings.Development.json
appsettings.*.Development.json
*.Development.json
.env
```

If you accidentally commit a secret:
1. Rotate the compromised key immediately (regenerate the API key in the respective service).
2. Use `git filter-branch` or BFG Repo Cleaner to remove the secret from git history.
3. Force push the cleaned history (coordinate with your team first).

---

## 6. Preparing the Legacy Config File

The agent reads a CSV file containing the list of legacy file configurations to migrate.

### 6.1 Expected CSV Format

The file should be located at `config/legacy-file-list.csv` relative to the project root. Expected format:

```csv
FileId,FileName,Protocol,Host,Port,RemotePath,LocalPattern,Schedule,PgpEncrypted,Notes
001,daily-report.csv,SFTP,sftp.vendor.com,22,/outbound/reports,daily-report-*.csv,0 6 * * *,false,Standard daily report
002,encrypted-feed.dat,SFTP,secure.partner.com,22,/data/feeds,feed-*.dat.pgp,0 */4 * * *,true,PGP encrypted - needs key ID 0xABCD1234
003,email-attachment.xlsx,EMAIL,outlook.office365.com,,inbox/finance,monthly-*.xlsx,0 8 1 * *,false,Exchange mailbox attachment
```

Column definitions:

| Column | Description | Required |
|---|---|---|
| `FileId` | Unique identifier for this file in the legacy system. | Yes |
| `FileName` | Human-readable file name or description. | Yes |
| `Protocol` | Transfer protocol: `SFTP`, `FTP`, `EMAIL`, `HTTP`. | Yes |
| `Host` | Hostname of the source server. | Yes |
| `Port` | Port number (blank for default). | No |
| `RemotePath` | Directory path on the remote server. | Yes |
| `LocalPattern` | Filename glob pattern to match. | Yes |
| `Schedule` | Cron expression for when to download. | Yes |
| `PgpEncrypted` | Whether the file is PGP encrypted (`true`/`false`). | Yes |
| `Notes` | Any additional context (key IDs, special handling, known issues). | No |

### 6.2 How to Export from the Legacy System

The exact export process depends on your legacy system. Common approaches:

1. **Database export**: If the legacy config is in a database, run a SQL query to extract all file configurations and export to CSV.
2. **Spreadsheet**: If the team maintains a spreadsheet tracking file configs, export it as CSV (File > Download > CSV in Google Sheets, or Save As CSV in Excel).
3. **Config file scraping**: If the legacy system uses flat config files, you may need to write a script to parse them into CSV format.

Whatever the source, ensure the CSV:
- Uses UTF-8 encoding.
- Has a header row matching the column names above.
- Has one row per file configuration.
- Does not contain trailing commas or blank rows at the end.

### 6.3 Place the File

```bash
# Create the config directory if it does not exist
mkdir -p /path/to/ftp-agent/config

# Copy or move your CSV file
cp /path/to/your/exported-file-list.csv /path/to/ftp-agent/config/legacy-file-list.csv

# Verify the file looks correct
head -5 /path/to/ftp-agent/config/legacy-file-list.csv
```

Verify the row count matches expectations:

```bash
wc -l /path/to/ftp-agent/config/legacy-file-list.csv
```

Expected: approximately 1401 lines (1 header + ~1400 data rows).

---

## 7. First Run

Follow these steps in order. Do not skip ahead -- each step validates a piece of the pipeline before you rely on it.

### 7.1 Clone the Repository (If Not Already Done)

```bash
cd /home/your-user
git clone git@github.com:your-org/ftp-agent.git
cd ftp-agent
```

### 7.2 Build the Project

```bash
dotnet restore src/FtpAgent/FtpAgent.csproj
dotnet build src/FtpAgent/FtpAgent.csproj --configuration Release
```

If the build succeeds, you will see:

```
Build succeeded.
    0 Warning(s)
    0 Error(s)
```

If it fails, check that:
- .NET 8 SDK is installed (`dotnet --version`).
- You are in the project root directory.
- NuGet package restore completed (check network connectivity).

### 7.3 Run in Dry-Run Mode

Dry-run mode uses the `StubDeploymentClient` and does not make real commits, deployments, or API calls (depending on implementation). It validates that the application starts, reads configuration, and can parse the legacy config file.

```bash
dotnet run --project src/FtpAgent -- --dry-run
```

Watch the console output. You should see:

```
info: FtpAgent.Program[0]
      FTP Agent starting. DryRun=True, Environment=Development
```

If it crashes immediately, the most common causes are:
- Missing `appsettings.json` in the output directory. Ensure the file is in `config/` and the `.csproj` copies it to the output.
- Missing or malformed `appsettings.Development.json`.
- Unreachable API endpoints (if any clients are initialized eagerly).

### 7.4 Verify Each Component Connects

Before running a full batch, test each external integration individually.

#### Test GitHub connectivity

```bash
# Verify gh CLI can access the target repo
gh repo view your-org/file-ingestion-app

# Verify you can list recent workflow runs
gh run list --repo your-org/file-ingestion-app --limit 5
```

#### Test git push access

```bash
# Clone the target repo to a temp directory and try a no-op push
cd /tmp
git clone git@github.com:your-org/file-ingestion-app.git test-push
cd test-push
git checkout -b test-agent-access
git commit --allow-empty -m "test: verify agent push access"
git push origin test-agent-access

# Clean up
git push origin --delete test-agent-access
cd /home/your-user/ftp-agent
rm -rf /tmp/test-push
```

#### Test Datadog API

Use the curl commands from Section 3.4.

#### Test Octopus Deploy API

Use the curl commands from Section 4.5.

#### Test Copilot / Claude Opus 4.5

```bash
gh copilot suggest "translate this SFTP config to YAML format: host=example.com, port=22, path=/data"
```

You should get an AI-generated response. If it times out or errors, check your Copilot subscription status.

### 7.5 Run a Single-File Test Batch

Once all components are verified, run the agent with a batch size of 1 to process a single file end-to-end:

```bash
# Override batch size via environment variable for this run
FTPAGENT_Agent__BatchSize=1 dotnet run --project src/FtpAgent
```

Monitor the output closely. The agent should:
1. Load one file from the legacy CSV.
2. Translate its config using Claude Opus 4.5.
3. Commit and push the new config to the target repo.
4. Wait for the GitHub Actions build to succeed.
5. Trigger an Octopus deployment.
6. Wait for the deployment to finish.
7. Query Datadog logs to verify the file downloads.
8. Report success or failure.

If any step fails, consult the [Troubleshooting](#8-troubleshooting) section below.

### 7.6 Scale Up

Once the single-file test succeeds:

```bash
# Process a small batch of 5
FTPAGENT_Agent__BatchSize=5 dotnet run --project src/FtpAgent

# If that works, run with the default batch size (from appsettings)
dotnet run --project src/FtpAgent
```

Monitor the first few batches carefully. Once you are confident, you can leave the agent running:

```bash
# Run in background with output logging
nohup dotnet run --project src/FtpAgent > /var/log/ftp-agent/agent.log 2>&1 &

# Or run in a tmux/screen session for easier monitoring
tmux new -s ftp-agent
dotnet run --project src/FtpAgent
# Detach with Ctrl+B, D
# Reattach with: tmux attach -t ftp-agent
```

For production use, consider setting up a systemd service:

```ini
# /etc/systemd/system/ftp-agent.service
[Unit]
Description=FTP Migration Agent
After=network.target

[Service]
Type=simple
User=ftp-agent
WorkingDirectory=/home/ftp-agent/ftp-agent
ExecStart=/usr/bin/dotnet run --project src/FtpAgent
Restart=on-failure
RestartSec=30
EnvironmentFile=/home/ftp-agent/.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ftp-agent
sudo systemctl start ftp-agent

# Check status
sudo systemctl status ftp-agent

# View logs
sudo journalctl -u ftp-agent -f
```

---

## 8. Troubleshooting

### 8.1 .NET SDK Not Found on PATH

**Symptom:** `dotnet: command not found` or `dotnet --version` returns nothing.

**Cause:** The .NET SDK is installed but not on your shell's `PATH`.

**Fix:**

```bash
# Find where dotnet was installed
find / -name "dotnet" -type f 2>/dev/null

# Common locations:
#   /usr/share/dotnet/dotnet
#   /usr/lib/dotnet/dotnet
#   /home/your-user/.dotnet/dotnet

# Add to PATH (replace with the actual directory containing the dotnet binary)
echo 'export PATH="$PATH:/usr/share/dotnet"' >> ~/.bashrc
source ~/.bashrc

# Verify
dotnet --version
```

If you installed via `snap`, the path may be `/snap/bin/dotnet`. If you installed via the install script to a custom location, use that location.

Also set `DOTNET_ROOT` so that tools can find the SDK:

```bash
echo 'export DOTNET_ROOT="/usr/share/dotnet"' >> ~/.bashrc
source ~/.bashrc
```

### 8.2 `gh auth` Issues

**Symptom:** `gh auth login` fails, or `gh auth status` shows an error.

**Possible causes and fixes:**

1. **Token is expired or revoked.**
   - Go to [https://github.com/settings/tokens](https://github.com/settings/tokens) and verify the token is still active.
   - If expired, generate a new token and run `gh auth login` again.

2. **Token does not have required scopes.**
   - Run `gh auth status` and check the listed scopes.
   - If `repo`, `workflow`, or `read:org` are missing, regenerate the token with the correct scopes.
   - Then: `gh auth login` with the new token.

3. **Behind a corporate proxy.**
   - Set the `HTTPS_PROXY` environment variable:
     ```bash
     export HTTPS_PROXY="http://proxy.your-company.com:8080"
     gh auth login
     ```

4. **GitHub Enterprise Server (not github.com).**
   - Use: `gh auth login --hostname github.your-company.com`

5. **Multiple accounts / conflicting auth.**
   - Clear existing auth: `gh auth logout`
   - Re-authenticate: `gh auth login`

### 8.3 SSH Key Permission Errors

**Symptom:** `git push` fails with `Permission denied (publickey)` or `ssh -T git@github.com` fails.

**Fixes:**

1. **Check file permissions.** SSH is very strict about permissions:
   ```bash
   ls -la ~/.ssh/

   # Fix permissions if wrong
   chmod 700 ~/.ssh
   chmod 600 ~/.ssh/id_ed25519
   chmod 644 ~/.ssh/id_ed25519.pub
   chmod 644 ~/.ssh/known_hosts
   ```

2. **Verify the key is added to GitHub.**
   ```bash
   # Show your public key fingerprint
   ssh-keygen -lf ~/.ssh/id_ed25519.pub

   # Compare with keys listed at https://github.com/settings/keys
   ```

3. **Check that ssh-agent has the key loaded (if using a passphrase).**
   ```bash
   eval "$(ssh-agent -s)"
   ssh-add ~/.ssh/id_ed25519

   # Verify
   ssh-add -l
   ```

4. **Check for SSH config conflicts.**
   ```bash
   cat ~/.ssh/config
   ```
   Make sure there is no `Host github.com` block pointing to a wrong key or user.

5. **Debug SSH connection.**
   ```bash
   ssh -vT git@github.com
   ```
   Look for lines like `Offering public key` and `Server accepts key` to understand what is happening.

### 8.4 Datadog API 403 Errors

**Symptom:** Curl to Datadog API returns HTTP 403 Forbidden.

**Possible causes and fixes:**

1. **Wrong API key.**
   - Double-check the key in your config against Datadog Organization Settings > API Keys.
   - API keys are 32 hex characters. Make sure you did not accidentally copy an Application key into the API key field (or vice versa).

2. **Wrong Application key.**
   - Application keys are tied to a specific user. If that user has been deactivated or had their role changed, the key may stop working.
   - Create a new Application key from your own account.

3. **Wrong Datadog site.**
   - If your org is on `datadoghq.eu` but you are hitting `api.datadoghq.com`, you will get 403.
   - Check the URL in your browser when you log into Datadog. See Section 3.3 for the mapping.

4. **Restricted roles.**
   - Some Datadog organizations restrict Logs API access to certain roles.
   - Ask your Datadog admin to ensure your user has the `Logs Read Data` permission.

5. **IP allowlist.**
   - Some Datadog organizations restrict API access by IP address.
   - Ask your admin if the VM's IP address is allowed.

### 8.5 Octopus Deploy API Connection Refused

**Symptom:** Curl to Octopus returns `Connection refused`, `Connection timed out`, or a TLS error.

**Possible causes and fixes:**

1. **Wrong server URL.**
   - Verify the URL is correct. Try opening it in a browser (or curl the root):
     ```bash
     curl -v https://octopus.your-company.com/api
     ```

2. **Network/firewall blocking.**
   - The VM may not have network access to the Octopus server.
   - Check with your network team. You may need a firewall rule or VPN.
   - Test basic connectivity:
     ```bash
     # Check if the port is reachable
     nc -zv octopus.your-company.com 443
     # or
     curl -v --connect-timeout 5 https://octopus.your-company.com
     ```

3. **TLS/SSL certificate issues.**
   - If Octopus uses a self-signed certificate or an internal CA:
     ```bash
     # See the certificate chain
     openssl s_client -connect octopus.your-company.com:443 -showcerts
     ```
   - You may need to add the CA certificate to the system trust store:
     ```bash
     # Ubuntu/Debian
     sudo cp your-ca.crt /usr/local/share/ca-certificates/
     sudo update-ca-certificates

     # RHEL/CentOS
     sudo cp your-ca.crt /etc/pki/ca-trust/source/anchors/
     sudo update-ca-trust
     ```

4. **Invalid API key.**
   - If you get `401 Unauthorized` instead of connection refused, the connection works but the key is wrong or expired.
   - Generate a new API key in Octopus (Section 4.2).

5. **Wrong Space ID.**
   - If you get `404 Not Found` when querying projects, you may be using the wrong Space ID.
   - Try `Spaces-1` (the default), or check the Octopus URL when navigating to your project.

### 8.6 Build Fails with NuGet Restore Errors

**Symptom:** `dotnet restore` or `dotnet build` fails with package download errors.

**Fixes:**

1. **No internet access from the VM.**
   ```bash
   # Test NuGet connectivity
   curl -s -o /dev/null -w "%{http_code}" https://api.nuget.org/v3/index.json
   ```
   Expected: `200`. If it fails, check proxy settings or firewall rules.

2. **Corporate proxy.**
   ```bash
   # Set proxy for dotnet
   export HTTP_PROXY="http://proxy.your-company.com:8080"
   export HTTPS_PROXY="http://proxy.your-company.com:8080"
   dotnet restore src/FtpAgent/FtpAgent.csproj
   ```

3. **Internal NuGet feed.**
   If your organization uses a private NuGet feed, add it:
   ```bash
   dotnet nuget add source "https://nuget.your-company.com/v3/index.json" --name internal
   ```

### 8.7 Copilot CLI Not Responding

**Symptom:** `gh copilot` hangs or times out.

**Fixes:**

1. **Check Copilot subscription.**
   - Visit [https://github.com/settings/copilot](https://github.com/settings/copilot) and confirm Copilot is enabled.

2. **Re-authenticate for Copilot scope.**
   ```bash
   gh auth refresh -s copilot
   ```

3. **Update the Copilot extension.**
   ```bash
   gh extension upgrade github/gh-copilot
   ```

4. **Check for rate limits.**
   - Copilot has usage limits, especially on free plans. If you are hitting rate limits, reduce `BatchSize` or add delays between translations.

5. **Increase timeout.**
   - If translations time out, increase `Copilot.TimeoutSeconds` in your config:
     ```json
     "Copilot": {
       "TimeoutSeconds": 300
     }
     ```

### 8.8 Agent Crashes on Startup with Configuration Errors

**Symptom:** The agent exits immediately with an error about missing or null configuration.

**Fixes:**

1. **Verify config file location.** The agent looks for `appsettings.json` relative to the binary output directory, not the project root. If running with `dotnet run`, the working directory should be the project root:
   ```bash
   # Run from the project root
   cd /path/to/ftp-agent
   dotnet run --project src/FtpAgent -- --dry-run
   ```

2. **Verify JSON syntax.** A single missing comma or extra trailing comma will cause a parse failure:
   ```bash
   # Validate JSON syntax
   python3 -c "import json; json.load(open('config/appsettings.Development.json'))"
   ```
   If it prints nothing, the JSON is valid. If it prints an error, fix the indicated line.

3. **Check environment variable names.** The prefix is `FTPAGENT_` (with underscore). Nesting uses double underscores: `FTPAGENT_GitHub__RepoOwner`. A common mistake is using single underscores or dots.

---

## Quick Reference: All Required Credentials

| Credential | Where to Get It | Config Field | Env Variable |
|---|---|---|---|
| GitHub PAT | github.com/settings/tokens | (used by `gh auth login`) | `GH_TOKEN` |
| Datadog API Key | Datadog Org Settings > API Keys | `Datadog.ApiKey` | `FTPAGENT_Datadog__ApiKey` |
| Datadog App Key | Datadog Org Settings > Application Keys | `Datadog.AppKey` | `FTPAGENT_Datadog__AppKey` |
| Octopus API Key | Octopus > Profile > API Keys | `OctopusDeploy.ApiKey` | `FTPAGENT_OctopusDeploy__ApiKey` |
| SSH Private Key | `ssh-keygen` on the VM | ~/.ssh/id_ed25519 | N/A (file-based) |

---

## Quick Reference: Verification Commands

Run these commands to confirm your setup is complete:

```bash
echo "=== 1. .NET SDK ==="
dotnet --version && echo "OK" || echo "FAIL"

echo ""
echo "=== 2. Git ==="
git --version && echo "OK" || echo "FAIL"

echo ""
echo "=== 3. GitHub CLI ==="
gh --version && echo "OK" || echo "FAIL"

echo ""
echo "=== 4. GitHub Auth ==="
gh auth status && echo "OK" || echo "FAIL"

echo ""
echo "=== 5. SSH to GitHub ==="
ssh -T git@github.com 2>&1 | grep -q "successfully authenticated" && echo "OK" || echo "FAIL (check SSH keys)"

echo ""
echo "=== 6. Copilot Extension ==="
gh copilot --version && echo "OK" || echo "FAIL"

echo ""
echo "=== 7. Project Build ==="
dotnet build src/FtpAgent/FtpAgent.csproj --nologo -v q && echo "OK" || echo "FAIL"

echo ""
echo "=== 8. Config File Exists ==="
test -f config/appsettings.Development.json && echo "OK" || echo "FAIL (copy from appsettings.json)"

echo ""
echo "=== 9. Legacy CSV Exists ==="
test -f config/legacy-file-list.csv && echo "OK" || echo "FAIL (see Section 6)"

echo ""
echo "Setup verification complete."
```
