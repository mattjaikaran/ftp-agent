# FTP Agent -- Business Case & Executive Summary

**Project:** FTP Agent -- Autonomous File Ingestion Migration
**Date:** February 2026
**Status:** In Development
**Stakeholders:** Engineering, Infrastructure, DevOps

---

## 1. Executive Summary

The organization operates a critical file ingestion pipeline that downloads files from hundreds of remote SFTP servers and Microsoft Exchange email accounts, deposits them into Amazon S3, and notifies downstream applications via Amazon SQS. This pipeline is being modernized: the underlying application has been re-architected as a Docker container running in Amazon EKS (Kubernetes), but its configuration format has changed. Approximately 1,400 file ingestion configurations must be migrated from the legacy proprietary format to a new JSON-based configuration system before the legacy platform can be decommissioned.

Today, this migration is performed manually by engineers. Each file requires translating the legacy config, committing it to Git, waiting for a CI/CD build-and-deploy cycle, verifying correctness in production logs, and diagnosing and fixing any errors that arise. This process takes 15 to 30 minutes per file and demands deep domain knowledge of SFTP protocols, PGP encryption, SSH key formats, and the legacy system's idiosyncrasies. At the current pace, completing the migration would consume an estimated 700 to 1,050 engineer-hours -- roughly 4 to 6 months of dedicated full-time effort from a senior engineer.

FTP Agent is an autonomous DevOps agent that eliminates this bottleneck. Built as a C# .NET 8 console application powered by Claude Opus 4.5 (via the GitHub Copilot agent framework), it automates the entire migration loop: AI-driven config translation, Git commit and push, GitHub Actions CI monitoring, Octopus Deploy triggering, Datadog log verification, AI-powered error diagnosis, config fix generation, and retry. The agent processes files in configurable batches, tracks state in a crash-resilient SQLite database, and escalates to a human only after exhausting its retry budget. Conservative estimates project a 10x reduction in engineer time and a path to completing the full migration in 2 to 4 weeks rather than months.

---

## 2. Problem Statement

### The Migration Challenge

The file ingestion platform handles approximately 1,400 active file configurations spanning SFTP, FTP, and Microsoft Exchange/email sources. Each configuration specifies connection details, authentication credentials, file naming patterns, PGP decryption settings, scheduling parameters, and downstream routing rules. All 1,400 must be translated from the legacy semi-structured format to the new application's JSON configuration schema.

### Quantified Cost of the Manual Process

| Metric | Value |
|---|---|
| Total files to migrate | ~1,400 |
| Time per file (manual) | 15--30 minutes |
| Average time per file (including retries) | ~30 minutes |
| Total estimated engineer-hours | 700--1,050 hours |
| Full-time equivalent (FTE) duration | 4--6 months (1 engineer) |
| First-attempt error rate (estimated) | 30--40% |
| Common error categories | PGP config, SSH key format mismatches, path pattern errors, connection timeouts |
| Engineers with required domain knowledge | 2--3 on the team |

### Opportunity Cost

While senior engineers are manually migrating configs, they are unavailable for higher-value work: building new features, improving reliability, reducing technical debt, or supporting other teams. The migration also creates a single-threaded dependency -- if the one or two engineers with the required domain knowledge are on vacation, sick, or pulled into incidents, the migration stalls entirely.

### Risk of the Status Quo

Every week the migration is not complete, the organization operates two parallel systems: the legacy platform and the new EKS-based platform. This dual operation increases operational overhead, monitoring complexity, and the surface area for incidents. Completing the migration faster directly reduces this risk.

---

## 3. Solution Overview

FTP Agent is an autonomous migration agent that replicates the full manual workflow in an automated, resilient loop.

### How It Works

1. **Load Batch** -- The agent reads the next batch of pending files from its SQLite state store (default batch size: 20 files).
2. **Translate Configs** -- For each file, Claude Opus 4.5 interprets the semi-structured legacy configuration and generates a correctly formatted JSON config for the new system. The AI is provided with curated translation examples and domain-specific rules.
3. **Commit and Push** -- The agent writes the new configs to the target repository, commits, and pushes to GitHub.
4. **Monitor CI Build** -- The agent polls GitHub Actions until the Docker image build succeeds or fails.
5. **Trigger Deployment** -- On successful build, the agent triggers a deployment via the Octopus Deploy REST API and waits for it to complete.
6. **Verify in Datadog** -- After deployment, the agent queries Datadog Logs to confirm that each file in the batch is downloading successfully.
7. **Diagnose and Fix Errors** -- For any file that shows errors in Datadog, Claude Opus 4.5 analyzes the error logs alongside the current config and generates a targeted fix (e.g., correcting a PGP key path, switching an SSH key format, adjusting a filename pattern).
8. **Retry or Escalate** -- The agent applies the fix and loops back to step 3. After a configurable maximum number of retries (default: 3), the file is flagged for manual intervention.
9. **Report** -- After all batches are processed, the agent generates a summary report of successes, failures, and files requiring human attention.

### Architecture at a Glance

```
Legacy Configs (CSV)
        |
        v
+-------------------+       +------------------+       +-------------------+
| ConfigTranslator  | ----> |   GitManager     | ----> | GitHub Actions    |
| (Claude Opus 4.5) |       | (commit & push)  |       | (CI build)        |
+-------------------+       +------------------+       +-------------------+
                                                                |
        +-------------------------------------------------------+
        |
        v
+-------------------+       +------------------+       +-------------------+
| Octopus Deploy    | ----> |  DatadogClient   | ----> | DiagnosticEngine  |
| (trigger deploy)  |       | (verify logs)    |       | (Claude Opus 4.5) |
+-------------------+       +------------------+       +-------------------+
                                                                |
                                                    (fix config, retry)
```

All state is persisted in SQLite. The agent can be stopped and restarted at any point without losing progress.

---

## 4. Key Technical Decisions

### Why C# and .NET 8

- The team's primary language is C#. Building the agent in C# means every engineer on the team can read, debug, and maintain it without learning a new stack.
- .NET 8 is the current LTS release with excellent cross-platform support (Linux, macOS, Windows) and strong performance characteristics.
- The target file ingestion application is also .NET-based, so shared domain models and configuration patterns reduce friction.

### Why Claude Opus 4.5

- The legacy configuration format is semi-structured and inconsistent. Deterministic parsers would require extensive special-casing for every edge case. An LLM with strong reasoning capabilities handles ambiguity naturally.
- Claude Opus 4.5 excels at structured output generation (JSON configs) and technical reasoning (diagnosing SFTP/PGP errors from log output).
- Accessed through the GitHub Copilot agent framework, which provides a supported and auditable integration path.

### Why Fully Autonomous

- The manual process has a well-defined, repeatable structure (translate, build, deploy, verify, fix, retry). Each step has clear success/failure criteria. This makes it an ideal candidate for full automation.
- Human-in-the-loop at every step would negate most of the time savings. The agent is designed to run unattended for hours, escalating only when it cannot resolve an issue within its retry budget.

### Why Batch Processing

- Deploying one file at a time would mean 1,400 separate build-deploy cycles, each taking 10 to 30 minutes. This would take weeks of wall-clock time just in CI/CD wait time.
- Batches of 20 files amortize the fixed cost of each build-deploy cycle across multiple files, dramatically reducing total wall-clock time.
- Batch size is configurable and can be tuned based on observed CI/CD throughput and error rates.

### Why SQLite for State

- The agent must be crash-resilient. If the process is killed, the VM reboots, or a network interruption occurs, the agent must resume from where it left off without re-processing already-migrated files.
- SQLite is zero-configuration, file-based, and requires no external infrastructure. It is the simplest reliable persistence option for a single-process console application.

---

## 5. Expected ROI

### Time Savings

| Metric | Manual | FTP Agent | Improvement |
|---|---|---|---|
| Time per file (avg) | 30 min | ~3 min | 10x faster |
| Time per batch of 20 | 10 hours | ~1 hour | 10x faster |
| Total migration time (engineer-hours) | 700--1,050 hrs | 70--105 hrs | 630--945 hrs saved |
| Total migration duration (wall-clock) | 4--6 months | 2--4 weeks | 3--5 months faster |
| Engineers required (dedicated) | 1--2 senior | 0.25 FTE (monitoring) | Frees 1--2 engineers |

**Assumptions:**
- Average 3 minutes of agent processing time per file (including retries), with additional CI/CD wait time amortized across batches.
- 70--105 hours accounts for agent setup, monitoring, and manual intervention on the estimated 5--10% of files the agent cannot resolve autonomously.
- Wall-clock estimate assumes the agent runs during business hours with periodic human oversight.

### Error Reduction

- The AI-powered translation is consistent: it applies the same rules to every file, eliminating the human errors that arise from fatigue, distraction, or unfamiliarity during repetitive manual work.
- The automated Datadog verification catches errors that a manual process might miss (e.g., a file that appears to deploy successfully but silently fails to download).
- The diagnostic engine accumulates pattern knowledge through its prompt templates, systematically addressing known error categories (PGP, key formats, path patterns).

### Faster Onboarding and Knowledge Preservation

- The agent's prompt templates and translation logic codify institutional knowledge about the legacy system's quirks. This knowledge is no longer locked in the heads of two or three senior engineers.
- New team members can review the agent's prompts and translation examples to understand the legacy-to-new mapping without needing months of hands-on experience.

---

## 6. Risk Mitigation

### Dry-Run Mode

The agent supports a `--dry-run` flag that executes the full workflow without making any changes: configs are translated but not committed, deployments are simulated, and Datadog queries return mock results. This allows the team to validate the agent's translation quality on real data before any production changes are made.

### Maximum Retry Limits

Each file has a configurable maximum retry count (default: 3). After exhausting retries, the file is marked as "failed -- needs manual intervention" and the agent moves on. This prevents the agent from entering infinite loops or making unbounded changes to a broken configuration.

### Human Escalation

Files that exceed the retry limit are surfaced in the agent's summary report with full context: the original legacy config, the attempted new config, the Datadog error logs, and the AI's diagnostic output. This gives the human reviewer everything they need to resolve the issue quickly.

### Atomic Batches and Rollback

Each batch is committed as a single Git commit with a descriptive message. If an entire batch causes problems, it can be reverted with a single `git revert`. The agent does not modify files outside its designated batch.

### State Persistence and Crash Recovery

SQLite state tracking ensures that if the agent is interrupted for any reason -- process crash, VM reboot, network outage -- it resumes from the last incomplete batch rather than starting over. No files are re-processed unnecessarily, and no files are skipped.

### Auditability

Every action the agent takes is logged with structured logging (via Microsoft.Extensions.Logging). Git commit history provides a complete audit trail of every config change. Datadog logs provide independent verification of each file's migration status.

### Blast Radius Control

- Batch size is configurable (default: 20) and can be reduced to 1 for cautious initial testing.
- The agent targets a specific environment (e.g., Development) and does not touch production until explicitly reconfigured.
- The agent operates on a designated branch and repository; it has no access to unrelated systems.

---

## 7. Success Metrics

The following metrics should be tracked to evaluate the agent's effectiveness:

| Metric | Target | How to Measure |
|---|---|---|
| First-attempt success rate | > 70% | Files that pass Datadog verification on the first try, divided by total files attempted |
| Overall success rate (with retries) | > 90% | Files successfully migrated (including retries), divided by total files attempted |
| Average time per file | < 5 minutes | Total elapsed time divided by number of files migrated (including CI/CD wait) |
| Files migrated per day | > 100 | Count of files marked "success" in the state store per calendar day |
| Manual intervention rate | < 10% | Files requiring human intervention, divided by total files attempted |
| Mean retries per file | < 1.5 | Total retry count across all files, divided by total files attempted |
| Migration completion date | Within 4 weeks of full rollout | Date when all 1,400 files are marked success or manually resolved |

### Monitoring Dashboard

A Datadog dashboard (or equivalent) should be created to track these metrics in near-real-time. The agent's structured logs provide the data source. Key views:

- Cumulative files migrated over time (line chart)
- Success vs. failure vs. pending breakdown (stacked bar)
- Error category distribution (pie chart: PGP, key format, path, connection, other)
- Average retry count trend (line chart)

---

## 8. Timeline and Rollout

The rollout follows a phased approach to minimize risk and build confidence incrementally.

### Phase 1: Dry-Run Validation (Week 1)

- Run the agent in `--dry-run` mode against all 1,400 legacy configs.
- Review a random sample of 50--100 translated configs for correctness.
- Measure first-attempt translation accuracy.
- Tune prompt templates and translation rules based on observed errors.
- **Exit criteria:** > 80% of sampled translations are correct or require only minor adjustments.

### Phase 2: Development Environment (Weeks 2--3)

- Run the agent in full autonomous mode against the Development environment.
- Start with small batches (5 files) and increase batch size as confidence grows.
- Target: migrate all 1,400 files through the Development environment.
- Monitor success rates, error patterns, and retry behavior.
- **Exit criteria:** > 85% overall success rate; no unexpected side effects; all error categories are understood.

### Phase 3: Staging Environment (Week 3--4)

- Re-run the agent against the Staging environment to validate configs in a production-like setting.
- Address any environment-specific issues (different SFTP endpoints, credentials, network paths).
- **Exit criteria:** > 90% overall success rate; < 10% manual intervention rate.

### Phase 4: Production Rollout (Weeks 4--5)

- Run the agent against Production in small batches (10 files), with an engineer monitoring.
- Gradually increase batch size and reduce monitoring frequency as confidence builds.
- Resolve any remaining manual-intervention files.
- **Exit criteria:** All 1,400 files migrated and verified; legacy system ready for decommission.

### Phase 5: Cleanup and Handoff (Week 6)

- Decommission the legacy file ingestion platform.
- Archive the agent code and documentation for future reference (the agent pattern may be reusable for other migration projects).
- Conduct a retrospective to capture lessons learned.

---

## 9. Team and Support

### Core Team

| Role | Responsibility |
|---|---|
| Agent Developer(s) | Build, test, and iterate on the FTP Agent codebase |
| Migration Lead | Monitor agent runs, review manual-intervention files, tune prompts |
| Infrastructure / DevOps | Ensure the agent has access to GitHub, Octopus Deploy, Datadog APIs; manage credentials |
| Domain Expert(s) | Provide legacy config samples, validate translation correctness, resolve edge cases |

### Day-to-Day Operations During Migration

- The Migration Lead reviews the agent's daily summary report each morning.
- Files flagged for manual intervention are triaged and resolved within 1 business day.
- Prompt templates are updated as new error patterns emerge.
- Batch size and retry limits are adjusted based on observed throughput and error rates.

### How to Get Help

- **Agent issues (bugs, crashes, unexpected behavior):** File an issue in the `ftp-agent` GitHub repository with the agent's log output and the relevant batch ID.
- **Translation quality issues:** Add the problematic legacy config and expected output to the `prompts/` directory as a new test case. Update the translation prompt template.
- **Infrastructure issues (API access, credentials, network):** Contact the Infrastructure / DevOps team via the standard support channel.
- **Questions about the legacy system:** Contact the Domain Expert(s) listed above.

### Post-Migration

After the migration is complete, the FTP Agent repository will be archived. The codebase, prompt templates, and documentation serve as a reference for future AI-assisted migration projects. No ongoing maintenance is required once all files are migrated and the legacy system is decommissioned.

---

## Appendix: Manual vs. Automated Comparison

| Dimension | Manual Process | FTP Agent (Automated) |
|---|---|---|
| **Config translation** | Engineer reads legacy config, manually writes JSON | Claude Opus 4.5 translates with curated examples |
| **Commit and push** | Engineer runs git commands | Agent commits with structured message |
| **CI build monitoring** | Engineer watches GitHub Actions UI | Agent polls API, waits for completion |
| **Deployment** | Engineer triggers via Octopus UI | Agent triggers via Octopus REST API |
| **Log verification** | Engineer searches Datadog manually | Agent queries Datadog Logs API |
| **Error diagnosis** | Engineer reads logs, uses experience | Claude Opus 4.5 analyzes logs and config |
| **Fix application** | Engineer edits config, re-commits | Agent generates and applies fix |
| **State tracking** | Spreadsheet or memory | SQLite database, crash-resilient |
| **Time per file** | 15--30 minutes | ~3 minutes (estimated) |
| **Runs unattended** | No | Yes |
| **Knowledge required** | Deep domain expertise | Encoded in prompts and templates |
| **Consistency** | Varies with fatigue and familiarity | Uniform across all files |
| **Audit trail** | Inconsistent | Full: Git history + structured logs |
