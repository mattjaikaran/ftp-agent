from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ftp_agent.ci.stub import StubCIMonitor
from ftp_agent.deployment.stub import StubDeploymentClient
from ftp_agent.diagnostics.engine import KNOWN_ISSUES, DiagnosticEngine
from ftp_agent.git.manager import GitManager
from ftp_agent.models.file_entry import FileEntry
from ftp_agent.monitoring.stub import StubMonitoringClient

# ------------------------------------------------------------------
# CI Stub
# ------------------------------------------------------------------


class TestStubCIMonitor:
    async def test_returns_success(self) -> None:
        monitor = StubCIMonitor()
        result = await monitor.wait_for_workflow("abc123")
        assert result.success is True
        assert result.run_id == "stub-run-1"
        assert result.conclusion == "success"

    async def test_respects_kwargs(self) -> None:
        monitor = StubCIMonitor()
        shutdown = asyncio.Event()
        result = await monitor.wait_for_workflow(
            "abc123",
            timeout_seconds=60,
            shutdown=shutdown,
        )
        assert result.success is True


# ------------------------------------------------------------------
# Deployment Stub
# ------------------------------------------------------------------


class TestStubDeploymentClient:
    async def test_trigger_returns_success(self) -> None:
        client = StubDeploymentClient()
        result = await client.trigger_deployment("1.0.0", "staging")
        assert result.success is True
        assert result.status == "Queued"
        assert result.deployment_id.startswith("stub-deploy-")

    async def test_wait_returns_success(self) -> None:
        client = StubDeploymentClient()
        result = await client.wait_for_deployment("stub-deploy-1")
        assert result.success is True
        assert result.status == "Success"
        assert result.deployment_id == "stub-deploy-1"


# ------------------------------------------------------------------
# Monitoring Stub
# ------------------------------------------------------------------


class TestStubMonitoringClient:
    async def test_returns_empty_success(self) -> None:
        client = StubMonitoringClient()
        result = await client.query_logs("test-file.dat")
        assert result.file_processed_successfully is True
        assert result.has_errors is False
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.error_messages == []
        assert result.warning_messages == []

    async def test_accepts_window_minutes(self) -> None:
        client = StubMonitoringClient()
        result = await client.query_logs("test-file.dat", window_minutes=30)
        assert result.file_processed_successfully is True


# ------------------------------------------------------------------
# GitManager
# ------------------------------------------------------------------


class TestGitManager:
    async def test_run_git_command_success(self) -> None:
        manager = GitManager("/tmp/test-repo")

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"abc1234\n", b"")
        mock_proc.returncode = 0

        with patch(
            "ftp_agent.git.manager.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await manager._run_git_command(
                "rev-parse",
                "--short",
                "HEAD",
            )

        assert result == "abc1234"

    async def test_run_git_command_failure_raises(self) -> None:
        manager = GitManager("/tmp/test-repo")

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b"",
            b"fatal: not a git repository\n",
        )
        mock_proc.returncode = 128

        with (
            patch(
                "ftp_agent.git.manager.asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ),
            pytest.raises(RuntimeError, match="Git command failed"),
        ):
            await manager._run_git_command("status")

    async def test_get_current_commit_hash(self) -> None:
        manager = GitManager("/tmp/test-repo")

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"deadbeef\n", b"")
        mock_proc.returncode = 0

        with patch(
            "ftp_agent.git.manager.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await manager.get_current_commit_hash()

        assert result == "deadbeef"

    async def test_get_current_branch(self) -> None:
        manager = GitManager("/tmp/test-repo")

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"feature/test\n", b"")
        mock_proc.returncode = 0

        with patch(
            "ftp_agent.git.manager.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await manager.get_current_branch()

        assert result == "feature/test"


# ------------------------------------------------------------------
# DiagnosticEngine: known issues
# ------------------------------------------------------------------


class TestDiagnosticEngineKnownIssues:
    def test_matches_file_not_found(self) -> None:
        result = DiagnosticEngine._check_known_issues(
            ["FileNotFoundException: /data/input.csv"],
        )
        assert "File path incorrect" in result

    def test_matches_connection_refused(self) -> None:
        result = DiagnosticEngine._check_known_issues(
            ["java.net.ConnectionRefused on port 22"],
        )
        assert "refusing connection" in result

    def test_matches_authentication_failed(self) -> None:
        result = DiagnosticEngine._check_known_issues(
            ["AuthenticationFailed for user admin"],
        )
        assert "Credential reference invalid" in result

    def test_matches_host_key_changed(self) -> None:
        result = DiagnosticEngine._check_known_issues(
            ["WARNING: HostKeyChanged detected"],
        )
        assert "host key mismatch" in result

    def test_matches_timeout(self) -> None:
        result = DiagnosticEngine._check_known_issues(
            ["TimeoutException after 30s"],
        )
        assert "timeout" in result.lower()

    def test_matches_permission_denied(self) -> None:
        result = DiagnosticEngine._check_known_issues(
            ["PermissionDenied on /remote/path"],
        )
        assert "permissions" in result.lower()

    def test_matches_certificate_error(self) -> None:
        result = DiagnosticEngine._check_known_issues(
            ["CertificateError: chain incomplete"],
        )
        assert "certificate" in result.lower()

    def test_matches_dns_resolution(self) -> None:
        result = DiagnosticEngine._check_known_issues(
            ["DnsResolutionFailed for sftp.example.com"],
        )
        assert "DNS" in result

    def test_matches_encoding_error(self) -> None:
        result = DiagnosticEngine._check_known_issues(
            ["EncodingError: invalid UTF-8 byte at offset 42"],
        )
        assert "encoding" in result.lower()

    def test_no_match_returns_empty(self) -> None:
        result = DiagnosticEngine._check_known_issues(
            ["everything is fine"],
        )
        assert result == ""

    def test_case_insensitive(self) -> None:
        result = DiagnosticEngine._check_known_issues(
            ["filenotfoundexception: missing"],
        )
        assert "File path incorrect" in result

    def test_all_known_issues_covered(self) -> None:
        assert len(KNOWN_ISSUES) == 9


# ------------------------------------------------------------------
# DiagnosticEngine: parse response
# ------------------------------------------------------------------


class TestDiagnosticEngineParseResponse:
    def test_valid_json_response(self) -> None:
        payload = json.dumps(
            {
                "analysis": "Port mismatch in config",
                "rootCause": "Wrong SFTP port",
                "isRecoverable": True,
                "suggestedChanges": ["Change port to 22"],
                "revisedConfig": '{"port": 22}',
            }
        )
        text = f"```json\n{payload}\n```"

        result = DiagnosticEngine._parse_response(text)

        assert result.analysis == "Port mismatch in config"
        assert result.root_cause == "Wrong SFTP port"
        assert result.is_recoverable is True
        assert result.suggested_changes == ["Change port to 22"]
        assert result.revised_config == '{"port": 22}'

    def test_valid_json_with_dict_revised_config(self) -> None:
        payload = json.dumps(
            {
                "analysis": "Config issue",
                "rootCause": "Bad host",
                "isRecoverable": False,
                "suggestedChanges": [],
                "revisedConfig": {"host": "sftp.example.com", "port": 22},
            }
        )
        text = f"```json\n{payload}\n```"

        result = DiagnosticEngine._parse_response(text)

        assert '"host": "sftp.example.com"' in result.revised_config
        assert '"port": 22' in result.revised_config

    def test_raw_json_without_fences(self) -> None:
        text = json.dumps(
            {
                "analysis": "Timeout issue",
                "rootCause": "Network latency",
                "isRecoverable": True,
                "suggestedChanges": ["Increase timeout"],
            }
        )

        result = DiagnosticEngine._parse_response(text)

        assert result.analysis == "Timeout issue"
        assert result.root_cause == "Network latency"
        assert result.is_recoverable is True

    def test_invalid_json_falls_back_to_text(self) -> None:
        text = "The error is caused by a misconfigured port."

        result = DiagnosticEngine._parse_response(text)

        assert result.analysis == text
        assert result.root_cause == "See analysis"
        assert result.is_recoverable is False
        assert result.suggested_changes == []
        assert result.revised_config == ""

    def test_partial_json_falls_back(self) -> None:
        text = '{"analysis": "partial", broken'

        result = DiagnosticEngine._parse_response(text)

        assert result.analysis == text
        assert result.root_cause == "See analysis"


# ------------------------------------------------------------------
# DiagnosticEngine: full diagnose flow
# ------------------------------------------------------------------


class TestDiagnosticEngineDiagnose:
    def _make_entry(self) -> FileEntry:
        return FileEntry(
            id="entry-1",
            name="transfer.xml",
            legacy_config="<old/>",
            new_config='{"host": "sftp.example.com"}',
            protocol="sftp",
        )

    async def test_diagnose_with_llm_success(self) -> None:
        mock_llm = MagicMock()
        response_json = json.dumps(
            {
                "analysis": "LLM analysis result",
                "rootCause": "Bad config",
                "isRecoverable": True,
                "suggestedChanges": ["Fix host"],
                "revisedConfig": "{}",
            }
        )
        mock_llm.chat = AsyncMock(
            return_value=MagicMock(
                content=f"```json\n{response_json}\n```",
            ),
        )

        engine = DiagnosticEngine(llm=mock_llm)
        entry = self._make_entry()
        result = await engine.diagnose(entry, ["ConnectionRefused"])

        assert result.analysis == "LLM analysis result"
        assert result.root_cause == "Bad config"
        assert result.is_recoverable is True
        mock_llm.chat.assert_called_once()

    async def test_diagnose_llm_failure_falls_back_to_known(self) -> None:
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(side_effect=RuntimeError("LLM down"))

        engine = DiagnosticEngine(llm=mock_llm)
        entry = self._make_entry()
        result = await engine.diagnose(
            entry,
            ["ConnectionRefused on port 22"],
        )

        assert "Known issue detected" in result.analysis
        assert "refusing connection" in result.root_cause
        assert result.is_recoverable is False

    async def test_diagnose_llm_failure_no_known_issues(self) -> None:
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(side_effect=RuntimeError("LLM down"))

        engine = DiagnosticEngine(llm=mock_llm)
        entry = self._make_entry()
        result = await engine.diagnose(entry, ["some unknown error"])

        assert "Diagnostic failed" in result.analysis
        assert result.root_cause == "Unknown"
        assert result.is_recoverable is False
