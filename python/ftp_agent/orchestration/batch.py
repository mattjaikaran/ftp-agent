"""BatchOrchestrator — main autonomous migration loop."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from ftp_agent.ci.protocol import CIMonitor
from ftp_agent.config.settings import AgentSettings
from ftp_agent.deployment.protocol import DeploymentClient
from ftp_agent.diagnostics.engine import DiagnosticEngine
from ftp_agent.git.manager import GitManager
from ftp_agent.models.file_entry import FileEntry, MigrationStatus
from ftp_agent.models.report import MigrationReport
from ftp_agent.models.results import BatchResult
from ftp_agent.monitoring.protocol import MonitoringClient
from ftp_agent.state.store import StateStore
from ftp_agent.translation.config_writer import ConfigWriter
from ftp_agent.translation.legacy_parser import LegacyConfigParser
from ftp_agent.translation.translator import ConfigTranslator

log = structlog.get_logger()


class BatchOrchestrator:
    """Process file migrations in batches: translate → commit → build → deploy → verify."""

    def __init__(
        self,
        settings: AgentSettings,
        state_store: StateStore,
        parser: LegacyConfigParser,
        translator: ConfigTranslator,
        config_writer: ConfigWriter,
        git_manager: GitManager,
        ci_monitor: CIMonitor,
        deployment_client: DeploymentClient,
        monitoring_client: MonitoringClient,
        diagnostic_engine: DiagnosticEngine,
    ) -> None:
        self._settings = settings
        self._store = state_store
        self._parser = parser
        self._translator = translator
        self._writer = config_writer
        self._git = git_manager
        self._ci = ci_monitor
        self._deploy = deployment_client
        self._monitor = monitoring_client
        self._diag = diagnostic_engine
        self._shutdown = asyncio.Event()
        self._batch_results: list[BatchResult] = []

    def request_stop(self) -> None:
        """Request graceful shutdown after current batch completes."""
        self._shutdown.set()
        log.info("orchestrator.stop_requested")

    async def run(self) -> MigrationReport:
        """Main entry point: initialize, load, process, report."""
        start = datetime.now(UTC)

        await self._store.initialize()
        await self._maybe_load_entries()

        batch_num = 0
        max_batches = self._settings.max_batches_per_run

        while await self._store.has_pending_files():
            if self._shutdown.is_set():
                log.info("orchestrator.shutdown")
                break

            if max_batches > 0 and batch_num >= max_batches:
                log.info("orchestrator.max_batches_reached", limit=max_batches)
                break

            batch_num += 1
            log.info("orchestrator.batch_start", batch=batch_num)

            result = await self._process_batch(batch_num)
            self._batch_results.append(result)

            log.info(
                "orchestrator.batch_complete",
                batch=batch_num,
                succeeded=len(result.succeeded),
                failed=len(result.failed),
                retrying=len(result.retrying),
                duration=str(result.duration),
            )

            if self._settings.stop_on_batch_failure and not result.all_succeeded:
                log.warning("orchestrator.stopping_on_batch_failure", batch=batch_num)
                break

        report = await self._store.generate_report()
        report.batch_results = self._batch_results
        report.total_duration = datetime.now(UTC) - start

        log.info("orchestrator.complete", summary=report.to_summary())
        return report

    async def _maybe_load_entries(self) -> None:
        """If DB is empty and a source path is configured, load entries from CSV."""
        source = self._settings.legacy_config_source_path
        if not source:
            return

        entries = await self._store.get_all_entries()
        if entries:
            log.info("orchestrator.entries_already_loaded", count=len(entries))
            return

        parsed = self._parser.parse_csv(source)
        if parsed:
            await self._store.load_entries(parsed)
            log.info("orchestrator.loaded_entries", count=len(parsed), source=source)

    async def _process_batch(self, batch_num: int) -> BatchResult:
        """Process a single batch of files through the full pipeline."""
        batch_start = datetime.now(UTC)
        batch = await self._store.get_next_batch(self._settings.batch_size)

        if not batch:
            return BatchResult(batch_number=batch_num)

        succeeded: list[FileEntry] = []
        failed: list[FileEntry] = []
        retrying: list[FileEntry] = []

        # Phase 1: Translate each file
        for entry in batch:
            if self._shutdown.is_set():
                break
            try:
                await self._store.mark_in_progress(entry.id)
                new_config = await self._translator.translate(entry)
                entry.new_config = new_config
                await self._store.update_new_config(entry.id, new_config)
                await self._writer.write_config(entry)
            except Exception as exc:
                log.exception("orchestrator.translate_failed", entry_id=entry.id)
                await self._handle_failure(entry, str(exc), failed, retrying)
                continue

        # Filter to only successfully translated entries
        translated = [e for e in batch if e.new_config and e not in failed and e not in retrying]
        if not translated:
            return BatchResult(
                batch_number=batch_num,
                failed=failed,
                retrying=retrying,
                duration=datetime.now(UTC) - batch_start,
            )

        # Phase 2: Commit and push
        names = ", ".join(e.name for e in translated[:5])
        commit_msg = f"migrate: batch {batch_num} - {len(translated)} file configs ({names})"
        try:
            commit_hash = await self._git.commit_and_push(commit_msg)
        except Exception as exc:
            log.exception("orchestrator.commit_failed", batch=batch_num)
            for entry in translated:
                await self._handle_failure(entry, f"Git error: {exc}", failed, retrying)
            return BatchResult(
                batch_number=batch_num,
                failed=failed,
                retrying=retrying,
                duration=datetime.now(UTC) - batch_start,
            )

        # Update commit hashes
        for entry in translated:
            entry.commit_hash = commit_hash
            await self._store.update_commit_hash(entry.id, commit_hash)

        # Phase 3: Wait for CI
        ci_timeout = self._settings.ci_build_timeout_minutes * 60
        build_result = await self._ci.wait_for_workflow(
            commit_hash,
            timeout_seconds=ci_timeout,
            shutdown=self._shutdown,
        )
        if not build_result.success:
            log.error("orchestrator.ci_failed", conclusion=build_result.conclusion)
            for entry in translated:
                await self._handle_failure(
                    entry,
                    f"CI failed: {build_result.conclusion}",
                    failed,
                    retrying,
                )
            return BatchResult(
                batch_number=batch_num,
                failed=failed,
                retrying=retrying,
                commit_hash=commit_hash,
                duration=datetime.now(UTC) - batch_start,
            )

        # Phase 4: Deploy
        deploy_result = await self._deploy.trigger_deployment(
            commit_hash,
            "production",
        )
        if not deploy_result.success:
            log.error("orchestrator.deploy_trigger_failed", error=deploy_result.error_message)
            for entry in translated:
                await self._handle_failure(
                    entry,
                    f"Deploy failed: {deploy_result.error_message}",
                    failed,
                    retrying,
                )
            return BatchResult(
                batch_number=batch_num,
                failed=failed,
                retrying=retrying,
                commit_hash=commit_hash,
                duration=datetime.now(UTC) - batch_start,
            )

        deploy_wait_timeout = self._settings.deploy_wait_timeout_minutes * 60
        deploy_result = await self._deploy.wait_for_deployment(
            deploy_result.deployment_id,
            timeout_seconds=deploy_wait_timeout,
        )
        if not deploy_result.success:
            log.error("orchestrator.deploy_failed", status=deploy_result.status)
            for entry in translated:
                await self._handle_failure(
                    entry,
                    f"Deploy failed: {deploy_result.status}",
                    failed,
                    retrying,
                )
            return BatchResult(
                batch_number=batch_num,
                failed=failed,
                retrying=retrying,
                commit_hash=commit_hash,
                deployment_id=deploy_result.deployment_id,
                duration=datetime.now(UTC) - batch_start,
            )

        # Update deployment IDs
        for entry in translated:
            entry.deployment_id = deploy_result.deployment_id
            await self._store.update_deployment_id(entry.id, deploy_result.deployment_id)

        # Phase 5: Wait for logs, then verify
        delay = self._settings.datadog_check_delay_minutes * 60
        if delay > 0:
            log.info("orchestrator.waiting_for_logs", delay_seconds=delay)
            await asyncio.sleep(delay)

        for entry in translated:
            if self._shutdown.is_set():
                break
            await self._verify_entry(entry, succeeded, failed, retrying)

        return BatchResult(
            batch_number=batch_num,
            succeeded=succeeded,
            failed=failed,
            retrying=retrying,
            commit_hash=commit_hash,
            deployment_id=deploy_result.deployment_id,
            duration=datetime.now(UTC) - batch_start,
        )

    async def _verify_entry(
        self,
        entry: FileEntry,
        succeeded: list[FileEntry],
        failed: list[FileEntry],
        retrying: list[FileEntry],
    ) -> None:
        """Verify a single entry via monitoring logs."""
        window = self._settings.log_query_window_minutes
        log_result = await self._monitor.query_logs(entry.name, window_minutes=window)

        if log_result.file_processed_successfully:
            await self._store.mark_success(entry.id)
            entry.status = MigrationStatus.SUCCESS
            succeeded.append(entry)
            log.info("orchestrator.entry_success", entry_id=entry.id)

        elif log_result.has_errors:
            diag = await self._diag.diagnose(entry, log_result.error_messages)
            if diag.is_recoverable and diag.revised_config:
                entry.new_config = diag.revised_config
                await self._store.update_new_config(entry.id, diag.revised_config)
                await self._store.increment_retry(entry.id, diag.root_cause)
                entry.status = MigrationStatus.RETRY_PENDING
                retrying.append(entry)
                log.info("orchestrator.entry_retrying", entry_id=entry.id, cause=diag.root_cause)
            else:
                await self._store.mark_failed(entry.id, diag.root_cause)
                entry.status = MigrationStatus.FAILED
                failed.append(entry)
                log.warning("orchestrator.entry_failed", entry_id=entry.id, cause=diag.root_cause)

        else:
            # No logs found yet — retry
            await self._store.increment_retry(entry.id, "No logs found in monitoring window")
            entry.status = MigrationStatus.RETRY_PENDING
            retrying.append(entry)
            log.info("orchestrator.entry_no_logs", entry_id=entry.id)

    async def _handle_failure(
        self,
        entry: FileEntry,
        error: str,
        failed: list[FileEntry],
        retrying: list[FileEntry],
    ) -> None:
        """Handle a file failure: retry if under limit, else mark permanently failed."""
        if entry.retry_count < self._settings.max_retries_per_file:
            await self._store.increment_retry(entry.id, error)
            entry.status = MigrationStatus.RETRY_PENDING
            retrying.append(entry)
        else:
            await self._store.mark_failed(entry.id, error)
            entry.status = MigrationStatus.FAILED
            failed.append(entry)
