from __future__ import annotations

from typing import Protocol, runtime_checkable

from ftp_agent.models.results import LogQueryResult


@runtime_checkable
class MonitoringClient(Protocol):
    """Protocol for log monitoring services."""

    async def query_logs(
        self,
        file_name: str,
        window_minutes: int = 15,
    ) -> LogQueryResult: ...
