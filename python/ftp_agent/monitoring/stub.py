from __future__ import annotations

import structlog

from ftp_agent.models.results import LogQueryResult

log = structlog.get_logger()


class StubMonitoringClient:
    """No-op monitoring client that always reports success."""

    async def query_logs(
        self,
        file_name: str,
        window_minutes: int = 15,
    ) -> LogQueryResult:
        log.info(
            "monitoring.stub.query_logs",
            file_name=file_name,
        )
        return LogQueryResult(file_processed_successfully=True)
