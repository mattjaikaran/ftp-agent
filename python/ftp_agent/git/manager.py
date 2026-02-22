from __future__ import annotations

import asyncio

import structlog

log = structlog.get_logger()

_CMD_TIMEOUT = 60


class GitManager:
    """Async git operations via subprocess for the target repository."""

    def __init__(self, repo_path: str) -> None:
        self._repo_path = repo_path

    async def commit_and_push(self, message: str) -> str:
        """Stage all, commit, push, and return the short commit hash."""
        await self._run_git_command("add", "-A")
        await self._run_git_command("commit", "-m", message)
        commit_hash = await self.get_current_commit_hash()
        await self._run_git_command("push")
        log.info("git.pushed", commit=commit_hash)
        return commit_hash

    async def checkout_branch(self, branch: str) -> None:
        await self._run_git_command("checkout", branch)
        log.info("git.checkout", branch=branch)

    async def pull(self) -> None:
        await self._run_git_command("pull", "--rebase")
        log.info("git.pulled")

    async def get_current_commit_hash(self) -> str:
        return await self._run_git_command("rev-parse", "--short", "HEAD")

    async def get_current_branch(self) -> str:
        return await self._run_git_command(
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
        )

    async def get_diff_summary(self) -> str:
        return await self._run_git_command("diff", "--stat")

    async def soft_reset_last_commit(self) -> None:
        await self._run_git_command("reset", "--soft", "HEAD~1")
        log.info("git.soft_reset")

    async def revert_commit(self, commit_hash: str) -> str:
        """Revert a specific commit and return the new revert commit hash."""
        await self._run_git_command("revert", "--no-edit", commit_hash)
        new_hash = await self.get_current_commit_hash()
        log.info("git.reverted", original=commit_hash, revert_commit=new_hash)
        return new_hash

    async def _run_git_command(self, *args: str) -> str:
        cmd = ["git", "-C", self._repo_path, *args]
        log.debug("git.exec", cmd=cmd)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=_CMD_TIMEOUT,
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            msg = f"Git command timed out after {_CMD_TIMEOUT}s: {cmd}"
            raise RuntimeError(msg) from exc

        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            msg = f"Git command failed (rc={proc.returncode}): {err}"
            raise RuntimeError(msg)

        return stdout.decode(errors="replace").strip()
