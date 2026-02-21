from __future__ import annotations

import asyncio

import structlog

from ftp_agent.models.results import BuildResult

log = structlog.get_logger()


class StubCIMonitor:
    """No-op CI monitor that always reports success."""

    async def wait_for_workflow(
        self,
        commit_hash: str,
        *,
        timeout_seconds: float = 1200,
        shutdown: asyncio.Event | None = None,
    ) -> BuildResult:
        log.info("ci.stub.wait_for_workflow", commit=commit_hash)
        await asyncio.sleep(0.1)
        return BuildResult(
            success=True,
            run_id="stub-run-1",
            conclusion="success",
        )
