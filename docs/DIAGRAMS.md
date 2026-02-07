# Diagrams

Visual aids for the FTP Agent architecture. All diagrams use [Mermaid](https://mermaid.js.org/) syntax and render natively on GitHub.

---

## 1. Autonomous Migration Loop (Flowchart)

The core feedback loop the agent executes for each batch of files.

```mermaid
flowchart TD
    Start([Agent Start]) --> Init[Initialize StateStore]
    Init --> HasPending{Has pending files?}

    HasPending -->|No| Report[Generate Migration Report]
    Report --> Done([Agent Complete])

    HasPending -->|Yes| LoadBatch[Load next batch from SQLite]
    LoadBatch --> Translate[Translate configs via Claude Opus 4.5]
    Translate --> WriteConfig[Write new configs to target repo]
    WriteConfig --> CommitPush[Git commit & push]

    CommitPush --> WaitBuild[Poll GitHub Actions for build status]
    WaitBuild --> BuildOK{Build succeeded?}

    BuildOK -->|No| DiagBuild[Diagnose build failure via Claude]
    DiagBuild --> FixBuild[Apply fix to config]
    FixBuild --> CommitPush

    BuildOK -->|Yes| Deploy[Trigger Octopus Deploy]
    Deploy --> WaitDeploy[Wait for deployment to complete]
    WaitDeploy --> DeployOK{Deploy succeeded?}

    DeployOK -->|No| LogDeployErr[Log deployment error]
    LogDeployErr --> HasPending

    DeployOK -->|Yes| WaitLogs[Wait for Datadog check delay]
    WaitLogs --> QueryDD[Query Datadog Logs API per file]

    QueryDD --> CheckFile{File downloaded OK?}

    CheckFile -->|Yes| MarkSuccess[Mark file as Success in SQLite]
    MarkSuccess --> MoreFiles{More files in batch?}

    CheckFile -->|No| UnderRetry{Under max retries?}

    UnderRetry -->|Yes| Diagnose[Diagnose error via Claude Opus 4.5]
    Diagnose --> ApplyFix[Apply suggested config fix]
    ApplyFix --> IncrRetry[Increment retry count in SQLite]
    IncrRetry --> MoreFiles

    UnderRetry -->|No| MarkFailed[Mark file as Failed in SQLite]
    MarkFailed --> MoreFiles

    MoreFiles -->|Yes| CheckFile
    MoreFiles -->|No| HasPending

    style Start fill:#4CAF50,color:#fff
    style Done fill:#4CAF50,color:#fff
    style MarkSuccess fill:#2196F3,color:#fff
    style MarkFailed fill:#f44336,color:#fff
    style Diagnose fill:#FF9800,color:#fff
    style DiagBuild fill:#FF9800,color:#fff
    style Translate fill:#9C27B0,color:#fff
```

---

## 2. File Migration State Machine

Lifecycle of a single file entry through the migration pipeline.

```mermaid
stateDiagram-v2
    [*] --> Pending: CSV imported

    Pending --> InProgress: Batch picked up
    InProgress --> Success: Datadog confirms download
    InProgress --> RetryPending: Recoverable error diagnosed
    InProgress --> Failed: Max retries exceeded

    RetryPending --> InProgress: Next batch picks it up

    Success --> [*]
    Failed --> [*]

    note right of Pending
        Status = 0
        Initial state for all files
    end note

    note right of InProgress
        Status = 1
        Being translated, built, deployed
    end note

    note right of Success
        Status = 2
        Verified in Datadog logs
    end note

    note right of Failed
        Status = 3
        Needs manual intervention
    end note

    note right of RetryPending
        Status = 4
        Queued for AI-assisted retry
    end note
```

---

## 3. Database Schema (SQLite)

The `file_entries` table in the SQLite state store.

```mermaid
erDiagram
    FILE_ENTRIES {
        TEXT id PK "Unique file identifier"
        TEXT name "Human-readable file name"
        TEXT legacy_config "Raw legacy configuration"
        TEXT new_config "Translated JSON config"
        INTEGER status "MigrationStatus enum (0-4)"
        INTEGER retry_count "Number of retry attempts"
        TEXT last_error "Most recent error message"
        TEXT created_at "ISO 8601 timestamp"
        TEXT updated_at "ISO 8601 timestamp"
        TEXT commit_hash "Git commit that deployed this config"
        TEXT deployment_id "Octopus deployment ID"
        TEXT source_path "Legacy config source path"
        TEXT destination_path "New config path in target repo"
        TEXT protocol "SFTP, FTP, EMAIL, HTTP"
    }
```

---

## 4. Component Dependency Graph

How the C# classes depend on each other via dependency injection.

```mermaid
graph TD
    Program[Program.cs<br/>Entry Point + DI] --> BO

    BO[BatchOrchestrator] --> LCP[LegacyConfigParser]
    BO --> CT[ConfigTranslator]
    BO --> NCW[NewConfigWriter]
    BO --> GM[GitManager]
    BO --> GAM[GitHubActionsMonitor]
    BO --> DC[IDeploymentClient]
    BO --> DDC[DatadogClient]
    BO --> DE[DiagnosticEngine]
    BO --> SS[StateStore]

    CT --> CCR[CopilotCliRunner]
    DE --> CCR
    CCR --> CopilotCLI{{Copilot CLI<br/>Claude Opus 4.5}}

    GM --> GitCLI{{git CLI}}
    GAM --> GHCLI{{gh CLI}}

    DC --> OctopusAPI{{Octopus Deploy<br/>REST API}}
    DDC --> DatadogAPI{{Datadog<br/>Logs API}}

    SS --> SQLite[(SQLite DB)]

    DC -.->|implements| ODC[OctopusDeployClient]
    DC -.->|implements| SDC[StubDeploymentClient]

    NCW --> TargetRepo{{Target Repo<br/>Config Files}}

    style BO fill:#1565C0,color:#fff
    style CCR fill:#673AB7,color:#fff
    style CopilotCLI fill:#9C27B0,color:#fff
    style GitCLI fill:#333,color:#fff
    style GHCLI fill:#333,color:#fff
    style OctopusAPI fill:#2E7D32,color:#fff
    style DatadogAPI fill:#7B1FA2,color:#fff
    style SQLite fill:#E65100,color:#fff
    style TargetRepo fill:#333,color:#fff
```

---

## 5. Sequence Diagram: Single Batch Migration

End-to-end flow for one batch of files.

```mermaid
sequenceDiagram
    participant O as BatchOrchestrator
    participant SS as StateStore
    participant CT as ConfigTranslator
    participant AI as Claude Opus 4.5
    participant CW as NewConfigWriter
    participant G as GitManager
    participant CI as GitHubActions
    participant OD as OctopusDeploy
    participant DD as DatadogClient
    participant DE as DiagnosticEngine

    O->>SS: GetNextBatch(20)
    SS-->>O: [file-001, file-002, ...]

    loop Each file in batch
        O->>SS: MarkInProgress(file.Id)
        O->>CT: TranslateAsync(legacyConfig)
        CT->>AI: Prompt with legacy config + examples
        AI-->>CT: Translated JSON config
        CT-->>O: newConfig
        O->>CW: WriteConfigAsync(file)
    end

    O->>G: CommitAndPushAsync("migrate: batch 1")
    G-->>O: commitHash = "abc123"

    O->>CI: WaitForWorkflowAsync("abc123", timeout)
    Note over CI: Polling GitHub Actions...
    CI-->>O: BuildResult { Success = true }

    O->>OD: TriggerDeploymentAsync(version, "dev")
    OD-->>O: deploymentId = "deploy-042"
    O->>OD: WaitForDeploymentAsync("deploy-042", timeout)
    Note over OD: Polling Octopus task...
    OD-->>O: DeploymentResult { Success = true }

    Note over O: Wait 5 min for files to download...

    loop Each file in batch
        O->>DD: QueryLogsAsync(file.Name, 30min)
        DD-->>O: LogQueryResult

        alt File processed successfully
            O->>SS: MarkSuccess(file.Id)
        else Recoverable error + retries left
            O->>DE: DiagnoseAsync(file, errors)
            DE->>AI: Prompt with error logs + config
            AI-->>DE: DiagnosticResult
            DE-->>O: { RootCause, SuggestedChanges }
            O->>SS: IncrementRetry(file.Id, error)
        else Max retries exceeded
            O->>SS: MarkFailed(file.Id, error)
        end
    end

    O->>SS: GenerateReport()
```

---

## 6. Infrastructure Overview

How the agent fits into the broader system architecture.

```mermaid
graph LR
    subgraph DevVM["Linux Dev VM"]
        Agent[FTP Agent<br/>.NET 8 Console App]
        SQLite[(SQLite<br/>State DB)]
        Agent --> SQLite
    end

    subgraph GitHub["GitHub"]
        Repo[File Ingestion<br/>App Repo]
        GHA[GitHub Actions<br/>Docker Build]
        Copilot[Copilot CLI<br/>Claude Opus 4.5]
        Repo --> GHA
    end

    subgraph Octopus["Octopus Deploy"]
        OctoDeploy[Deployment<br/>Pipeline]
    end

    subgraph AWS["AWS"]
        EKS[EKS Kubernetes]
        Docker[File Ingestion<br/>Docker Container]
        S3[(S3 Bucket)]
        SQS[SQS Queue]
        EKS --> Docker
        Docker --> S3
        Docker --> SQS
    end

    subgraph Sources["File Sources"]
        SFTP[SFTP Servers<br/>~hundreds]
        Exchange[Outlook/Exchange<br/>Email Attachments]
    end

    subgraph Monitoring["Monitoring"]
        Datadog[Datadog<br/>Logs + Metrics]
    end

    subgraph Downstream["Downstream"]
        Apps[Downstream<br/>Applications]
    end

    Agent -->|git push| Repo
    Agent -->|poll builds| GHA
    Agent -->|AI prompts| Copilot
    Agent -->|trigger deploy| OctoDeploy
    Agent -->|query logs| Datadog
    GHA -->|push image| EKS
    OctoDeploy -->|deploy to| EKS
    Docker -->|download from| SFTP
    Docker -->|download from| Exchange
    Docker -->|logs to| Datadog
    SQS -->|notify| Apps

    style Agent fill:#1565C0,color:#fff
    style Docker fill:#0288D1,color:#fff
    style Copilot fill:#9C27B0,color:#fff
    style Datadog fill:#7B1FA2,color:#fff
    style SQLite fill:#E65100,color:#fff
```

---

## 7. Config Translation Data Flow

How a legacy config becomes a deployed new config.

```mermaid
flowchart LR
    CSV[legacy-file-list.csv<br/>~1400 rows] -->|LegacyConfigParser| Parsed[Parsed FileEntry<br/>objects]
    Parsed -->|ConfigTranslator| Prompt[Prompt Template<br/>+ Legacy Config]
    Prompt -->|Copilot CLI| Claude[Claude Opus 4.5]
    Claude --> JSON[Translated JSON<br/>Config]
    JSON -->|NewConfigWriter| Repo[Target Repo<br/>configs/sftp/file.json]
    Repo -->|git push| GHA[GitHub Actions<br/>Docker Build]
    GHA --> Image[Docker Image<br/>with new configs]
    Image -->|Octopus Deploy| EKS[EKS Pod<br/>picks up config]
    EKS -->|Downloads file| S3[File in S3]

    style CSV fill:#FFB300,color:#000
    style Claude fill:#9C27B0,color:#fff
    style S3 fill:#4CAF50,color:#fff
```

---

## 8. Retry & Diagnosis Flow

What happens when a file fails and the agent diagnoses the issue.

```mermaid
flowchart TD
    Fail[Datadog: File download failed] --> GetLogs[Pull error logs from Datadog]
    GetLogs --> KnownCheck{Match known<br/>error pattern?}

    KnownCheck -->|Yes| FastFix[Apply known fix<br/>without LLM call]
    KnownCheck -->|No| LLMDiag[Send to Claude Opus 4.5<br/>with error logs + config]

    LLMDiag --> Parse[Parse DiagnosticResult]
    Parse --> Recoverable{Is recoverable?}

    Recoverable -->|No| MarkFail[Mark as Failed<br/>needs manual intervention]

    Recoverable -->|Yes| ApplyChanges[Apply suggested<br/>config changes]
    FastFix --> ApplyChanges

    ApplyChanges --> CheckRetry{Retry count<br/>< max retries?}

    CheckRetry -->|Yes| Queue[Queue as RetryPending<br/>for next batch cycle]
    CheckRetry -->|No| MarkFail

    Queue --> NextBatch[Picked up in<br/>next batch]
    NextBatch --> Redeploy[Commit → Build → Deploy<br/>→ Check Datadog again]

    style Fail fill:#f44336,color:#fff
    style FastFix fill:#FF9800,color:#fff
    style LLMDiag fill:#9C27B0,color:#fff
    style MarkFail fill:#f44336,color:#fff
    style Queue fill:#2196F3,color:#fff
    style Redeploy fill:#4CAF50,color:#fff
```

---

## 9. Batch Processing Timeline

Typical timeline for a single batch cycle.

```mermaid
gantt
    title Batch Migration Cycle Timeline
    dateFormat mm:ss
    axisFormat %M:%S

    section Config
    Translate 20 files (AI)       :active, t1, 00:00, 02:00
    Write configs to repo         :t2, after t1, 00:15

    section Git + CI
    Git commit & push             :t3, after t2, 00:10
    GitHub Actions build          :crit, t4, after t3, 08:00

    section Deploy
    Trigger Octopus deployment    :t5, after t4, 00:15
    Wait for deployment           :t6, after t5, 05:00

    section Verify
    Wait for download delay       :t7, after t6, 05:00
    Query Datadog per file        :t8, after t7, 01:00
    Diagnose failures (AI)        :t9, after t8, 01:00
```

---

## 10. Class Diagram: Core Models

The data models used throughout the pipeline.

```mermaid
classDiagram
    class FileEntry {
        +string Id
        +string Name
        +string LegacyConfig
        +string NewConfig
        +MigrationStatus Status
        +int RetryCount
        +string LastError
        +DateTime CreatedAt
        +DateTime UpdatedAt
        +string CommitHash
        +string DeploymentId
        +string SourcePath
        +string DestinationPath
        +string Protocol
        +ToString() string
    }

    class MigrationStatus {
        <<enumeration>>
        Pending = 0
        InProgress = 1
        Success = 2
        Failed = 3
        RetryPending = 4
    }

    class BatchResult {
        +int BatchNumber
        +List~FileEntry~ Succeeded
        +List~FileEntry~ Failed
        +List~FileEntry~ Retrying
        +TimeSpan Duration
        +string CommitHash
        +string DeploymentId
        +int TotalProcessed
        +bool AllSucceeded
    }

    class MigrationReport {
        +DateTime GeneratedAt
        +int TotalFiles
        +int Succeeded
        +int Failed
        +int Pending
        +int InProgress
        +int RetryPending
        +TimeSpan TotalDuration
        +List~FileEntry~ FailedEntries
        +List~BatchResult~ BatchResults
        +double SuccessRate
        +ToSummary() string
    }

    class BuildResult {
        +bool Success
        +string RunId
        +string Conclusion
        +string LogOutput
        +string Url
    }

    class DeploymentResult {
        +bool Success
        +string DeploymentId
        +string Status
        +string ErrorMessage
    }

    class LogQueryResult {
        +bool HasErrors
        +int TotalLogEntries
        +int ErrorCount
        +int WarningCount
        +List~string~ ErrorMessages
        +List~string~ WarningMessages
        +bool FileProcessedSuccessfully
    }

    class DiagnosticResult {
        +string Analysis
        +List~string~ SuggestedChanges
        +string RevisedConfig
        +bool IsRecoverable
        +string RootCause
    }

    FileEntry --> MigrationStatus
    BatchResult --> FileEntry
    MigrationReport --> FileEntry
    MigrationReport --> BatchResult
```
