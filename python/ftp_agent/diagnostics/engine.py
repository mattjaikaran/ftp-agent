from __future__ import annotations

import json
import re
from pathlib import Path

import structlog

from ftp_agent.llm.protocol import LLMMessage, LLMProvider
from ftp_agent.models.file_entry import FileEntry
from ftp_agent.models.results import DiagnosticResult

log = structlog.get_logger()

KNOWN_ISSUES: dict[str, str] = {
    "FileNotFoundException": ("File path incorrect or file does not exist at source"),
    "ConnectionRefused": ("Remote host refusing connection - check host/port/firewall"),
    "AuthenticationFailed": ("Credential reference invalid - verify vault path"),
    "HostKeyChanged": ("SSH host key mismatch - update known_hosts"),
    "TimeoutException": ("Connection timeout - increase timeout or check network"),
    "PermissionDenied": ("Insufficient permissions on remote path"),
    "CertificateError": ("TLS certificate validation failed - check cert chain"),
    "DnsResolutionFailed": ("DNS lookup failed - verify hostname"),
    "EncodingError": ("File encoding mismatch - check UTF-8 vs legacy encoding"),
}


class DiagnosticEngine:
    """Diagnose file migration errors using known patterns and LLM."""

    def __init__(
        self,
        llm: LLMProvider,
        prompt_path: str = "prompts/error-diagnosis.md",
    ) -> None:
        self._llm = llm
        self._prompt_path = prompt_path

    async def diagnose(
        self,
        entry: FileEntry,
        error_messages: list[str],
    ) -> DiagnosticResult:
        # Check known issues first
        known = self._check_known_issues(error_messages)

        # Call LLM for deeper analysis
        try:
            return await self._llm_diagnose(entry, error_messages, known)
        except Exception:
            log.exception("diagnostics.llm_failed", entry_id=entry.id)
            # Fall back to known issues only
            if known:
                return DiagnosticResult(
                    analysis=f"Known issue detected: {known}",
                    root_cause=known,
                    is_recoverable=False,
                    suggested_changes=[known],
                )
            return DiagnosticResult(
                analysis="Diagnostic failed and no known issues matched.",
                root_cause="Unknown",
                is_recoverable=False,
            )

    @staticmethod
    def _check_known_issues(error_messages: list[str]) -> str:
        combined = " ".join(error_messages)
        for pattern, resolution in KNOWN_ISSUES.items():
            if pattern.lower() in combined.lower():
                return resolution
        return ""

    async def _llm_diagnose(
        self,
        entry: FileEntry,
        error_messages: list[str],
        known_issues: str,
    ) -> DiagnosticResult:
        prompt_template = self._load_prompt()
        prompt = (
            prompt_template.replace("{{FILE_NAME}}", entry.name)
            .replace("{{FILE_ID}}", entry.id)
            .replace("{{PROTOCOL}}", entry.protocol)
            .replace("{{RETRY_COUNT}}", str(entry.retry_count))
            .replace("{{CURRENT_CONFIG}}", entry.new_config)
            .replace("{{LEGACY_CONFIG}}", entry.legacy_config)
            .replace("{{ERROR_LOGS}}", "\n".join(error_messages))
            .replace(
                "{{KNOWN_ISSUES}}",
                known_issues or "None detected.",
            )
        )

        messages = [
            LLMMessage(
                role="system",
                content="You are a DevOps diagnostic specialist.",
            ),
            LLMMessage(role="user", content=prompt),
        ]

        response = await self._llm.chat(messages)
        return self._parse_response(response.content)

    def _load_prompt(self) -> str:
        path = Path(self._prompt_path)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return "Diagnose the following error:\n{{ERROR_LOGS}}\n\nConfig:\n{{CURRENT_CONFIG}}"

    @staticmethod
    def _parse_response(text: str) -> DiagnosticResult:
        # Try to extract JSON from fenced code block first
        json_match = re.search(
            r"```json\s*\n(.*?)\n\s*```",
            text,
            re.DOTALL,
        )
        raw = json_match.group(1) if json_match else text

        try:
            data = json.loads(raw)
            revised = data.get("revisedConfig", "")
            if isinstance(revised, dict):
                revised = json.dumps(revised, indent=2)
            return DiagnosticResult(
                analysis=data.get("analysis", ""),
                root_cause=data.get("rootCause", ""),
                is_recoverable=data.get("isRecoverable", False),
                suggested_changes=data.get("suggestedChanges", []),
                revised_config=revised,
            )
        except (json.JSONDecodeError, AttributeError):
            return DiagnosticResult(
                analysis=text,
                root_cause="See analysis",
                is_recoverable=False,
            )
