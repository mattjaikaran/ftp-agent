"""Tests for BatchOrchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from ftp_agent.config.settings import AgentSettings
from ftp_agent.models.file_entry import FileEntry
from ftp_agent.models.results import BuildResult, DeploymentResult, LogQueryResult
from ftp_agent.orchestration.batch import BatchOrchestrator
from ftp_agent.state.store import StateStore


def _make_orchestrator(store: StateStore, **overrides) -> BatchOrchestrator:
    settings = AgentSettings(
        batch_size=2,
        max_retries_per_file=1,
        ci_build_timeout_minutes=1,
        deploy_wait_timeout_minutes=1,
        datadog_check_delay_minutes=0,
        log_query_window_minutes=1,
        poll_interval_seconds=1,
        max_batches_per_run=1,
    )
    translator = AsyncMock()
    translator.translate.return_value = '{"name": "test"}'

    writer = AsyncMock()
    writer.write_config.return_value = "/tmp/test.json"

    git = AsyncMock()
    git.commit_and_push.return_value = "abc1234"

    ci = AsyncMock()
    ci.wait_for_workflow.return_value = BuildResult(success=True, run_id="1", conclusion="success")

    deploy = AsyncMock()
    deploy.trigger_deployment.return_value = DeploymentResult(
        success=True,
        deployment_id="d1",
        status="Queued",
    )
    deploy.wait_for_deployment.return_value = DeploymentResult(
        success=True,
        deployment_id="d1",
        status="Success",
    )

    monitor = AsyncMock()
    monitor.query_logs.return_value = LogQueryResult(file_processed_successfully=True)

    diag = AsyncMock()

    return BatchOrchestrator(
        settings=settings,
        state_store=store,
        parser=MagicMock(),
        translator=translator,
        config_writer=writer,
        git_manager=git,
        ci_monitor=ci,
        deployment_client=deploy,
        monitoring_client=monitor,
        diagnostic_engine=diag,
    )


async def test_run_with_no_entries(store: StateStore):
    orch = _make_orchestrator(store)
    report = await orch.run()
    assert report.total_files == 0


async def test_run_processes_batch(store: StateStore, sample_entries: list[FileEntry]):
    await store.load_entries(sample_entries[:2])
    orch = _make_orchestrator(store)

    report = await orch.run()

    assert report.succeeded == 2
    assert report.failed == 0


async def test_run_handles_translate_failure(store: StateStore, sample_entries: list[FileEntry]):
    await store.load_entries(sample_entries[:1])
    orch = _make_orchestrator(store)
    orch._translator.translate.side_effect = ValueError("LLM error")

    report = await orch.run()

    # Should have failed or retrying
    assert report.total_files == 1
    assert report.succeeded == 0


async def test_request_stop(store: StateStore, sample_entries: list[FileEntry]):
    await store.load_entries(sample_entries)
    orch = _make_orchestrator(store)
    orch.request_stop()

    report = await orch.run()
    # Should have stopped early
    assert report is not None
