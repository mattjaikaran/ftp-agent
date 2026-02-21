from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from ftp_agent.models.results import BuildResult


@runtime_checkable
class CIMonitor(Protocol):
    """Protocol for CI build monitoring services."""

    async def wait_for_workflow(
        self,
        commit_hash: str,
        *,
        timeout_seconds: float = 1200,
        shutdown: asyncio.Event | None = None,
    ) -> BuildResult: ...
