from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from ftp_agent.config.settings import AgentSettings, DatadogSettings
from ftp_agent.models.results import LogQueryResult

log = structlog.get_logger()

_ERROR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"FileNotFoundException",
        r"ConnectionRefused",
        r"AuthenticationFailed",
        r"TimeoutException",
        r"PermissionDenied",
        r"CertificateError",
        r"DnsResolutionFailed",
        r"EncodingError",
        r"HostKeyChanged",
        r"\bERROR\b",
        r"\bFATAL\b",
        r"Exception",
    ]
]

_WARNING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bWARN(?:ING)?\b",
        r"retry",
        r"slow",
        r"deprecated",
    ]
]

_SUCCESS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"File processed successfully",
        r"Ingestion complete",
        r"Transfer completed",
    ]
]


class DatadogClient:
    """Datadog Logs API client for post-deployment monitoring."""

    def __init__(
        self,
        settings: DatadogSettings,
        agent: AgentSettings,
    ) -> None:
        self._settings = settings
        self._agent = agent
        self._client = httpx.AsyncClient(
            base_url=settings.api_url,
            headers={
                "DD-API-KEY": settings.api_key.get_secret_value(),
                "DD-APPLICATION-KEY": settings.app_key.get_secret_value(),
                "Content-Type": "application/json",
            },
            timeout=30,
        )

    async def query_logs(
        self,
        file_name: str,
        window_minutes: int = 15,
    ) -> LogQueryResult:
        now = datetime.now(UTC)
        from_time = now - timedelta(minutes=window_minutes)

        query = (
            f'service:{self._settings.service_name} env:{self._settings.environment} "{file_name}"'
        )

        try:
            resp = await self._client.post(
                "/api/v2/logs/events/search",
                json={
                    "filter": {
                        "query": query,
                        "from": from_time.isoformat(),
                        "to": now.isoformat(),
                    },
                    "sort": "-timestamp",
                    "page": {"limit": 500},
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            log.exception(
                "monitoring.query_failed",
                file_name=file_name,
            )
            return LogQueryResult(has_errors=True, error_count=1)

        events: list[dict[str, Any]] = data.get("data", [])
        return self._parse_events(events)

    def _parse_events(self, events: list[dict[str, Any]]) -> LogQueryResult:
        error_messages: list[str] = []
        warning_messages: list[str] = []
        file_success = False

        for event in events:
            message = event.get("attributes", {}).get("message", "")
            if not message:
                continue

            if any(p.search(message) for p in _ERROR_PATTERNS):
                error_messages.append(message)

            if any(p.search(message) for p in _WARNING_PATTERNS):
                warning_messages.append(message)

            if any(p.search(message) for p in _SUCCESS_PATTERNS):
                file_success = True

        return LogQueryResult(
            has_errors=len(error_messages) > 0,
            total_log_entries=len(events),
            error_count=len(error_messages),
            warning_count=len(warning_messages),
            error_messages=error_messages,
            warning_messages=warning_messages,
            file_processed_successfully=file_success,
        )

    async def close(self) -> None:
        await self._client.aclose()
