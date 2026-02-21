from __future__ import annotations

import asyncio
import json

import structlog

from ftp_agent.config.settings import AgentSettings, GitHubSettings
from ftp_agent.models.results import BuildResult

log = structlog.get_logger()

_MAX_LOG_BYTES = 50_000


class GitHubActionsMonitor:
    """Monitor GitHub Actions CI workflows via the ``gh`` CLI."""

    def __init__(self, github: GitHubSettings, agent: AgentSettings) -> None:
        self._github = github
        self._poll_interval = agent.poll_interval_seconds

    async def wait_for_workflow(
        self,
        commit_hash: str,
        *,
        timeout_seconds: float = 1200,
        shutdown: asyncio.Event | None = None,
    ) -> BuildResult:
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        run_id: str | None = None

        # Phase 1: find the run triggered by this commit
        while asyncio.get_event_loop().time() < deadline:
            if shutdown and shutdown.is_set():
                return BuildResult(success=False, conclusion="cancelled")

            runs = await self._list_runs(commit_hash)
            if runs:
                run_id = str(runs[0]["databaseId"])
                log.info(
                    "ci.found_run",
                    run_id=run_id,
                    commit=commit_hash,
                )
                break

            await asyncio.sleep(self._poll_interval)

        if not run_id:
            return BuildResult(success=False, conclusion="not_found")

        # Phase 2: wait until the run completes
        while asyncio.get_event_loop().time() < deadline:
            if shutdown and shutdown.is_set():
                return BuildResult(
                    success=False,
                    run_id=run_id,
                    conclusion="cancelled",
                )

            runs = await self._list_runs(commit_hash)
            if runs and runs[0].get("status") == "completed":
                conclusion = runs[0].get("conclusion", "unknown")
                log_output = await self._get_logs(run_id)
                url = f"https://github.com/{self._github.repository}/actions/runs/{run_id}"
                return BuildResult(
                    success=conclusion == "success",
                    run_id=run_id,
                    conclusion=conclusion,
                    log_output=log_output[:_MAX_LOG_BYTES],
                    url=url,
                )

            await asyncio.sleep(self._poll_interval)

        return BuildResult(
            success=False,
            run_id=run_id or "",
            conclusion="timed_out",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _list_runs(self, commit_hash: str) -> list[dict]:
        cmd: list[str] = [
            "gh",
            "run",
            "list",
            "--repo",
            self._github.repository,
            "--commit",
            commit_hash,
            "--json",
            "databaseId,status,conclusion",
            "--limit",
            "1",
        ]
        if self._github.workflow_name:
            cmd.extend(["--workflow", self._github.workflow_name])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return json.loads(stdout.decode())  # type: ignore[no-any-return]
        except Exception:
            log.exception("ci.list_runs_failed")
        return []

    async def _get_logs(self, run_id: str) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "gh",
                "run",
                "view",
                run_id,
                "--repo",
                self._github.repository,
                "--log",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return stdout.decode(errors="replace")
        except Exception:
            log.exception("ci.get_logs_failed")
        return ""
