from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from ftp_agent.config.settings import AgentSettings, OctopusSettings
from ftp_agent.models.results import DeploymentResult

log = structlog.get_logger()


class OctopusDeployClient:
    """Octopus Deploy REST API client."""

    def __init__(
        self,
        settings: OctopusSettings,
        agent: AgentSettings,
    ) -> None:
        self._settings = settings
        self._poll_interval = agent.poll_interval_seconds
        self._client = httpx.AsyncClient(
            base_url=settings.server_url,
            headers={
                "X-Octopus-ApiKey": settings.api_key.get_secret_value(),
            },
            timeout=30,
        )

    async def trigger_deployment(
        self,
        version: str,
        environment: str,
    ) -> DeploymentResult:
        try:
            space = self._settings.space_id

            # Create release
            release_resp = await self._client.post(
                f"/api/{space}/releases",
                json={
                    "ProjectId": self._settings.project_name,
                    "Version": version,
                },
            )
            release_resp.raise_for_status()
            release_id = release_resp.json()["Id"]

            # Resolve environment ID
            env_name = environment or self._settings.environment_name
            env_resp = await self._client.get(
                f"/api/{space}/environments",
                params={"name": env_name},
            )
            env_resp.raise_for_status()
            envs: list[dict[str, Any]] = env_resp.json().get("Items", [])
            if not envs:
                return DeploymentResult(
                    success=False,
                    status="Failed",
                    error_message=f"Environment '{env_name}' not found",
                )
            env_id = envs[0]["Id"]

            # Create deployment
            deploy_resp = await self._client.post(
                f"/api/{space}/deployments",
                json={
                    "ReleaseId": release_id,
                    "EnvironmentId": env_id,
                },
            )
            deploy_resp.raise_for_status()
            deployment_id = deploy_resp.json()["Id"]

            log.info(
                "deployment.triggered",
                deployment_id=deployment_id,
                version=version,
            )
            return DeploymentResult(
                success=True,
                deployment_id=deployment_id,
                status="Queued",
            )
        except httpx.HTTPError as exc:
            log.exception("deployment.trigger_failed")
            return DeploymentResult(
                success=False,
                status="Failed",
                error_message=str(exc),
            )

    async def wait_for_deployment(
        self,
        deployment_id: str,
        timeout_seconds: float = 1800,
    ) -> DeploymentResult:
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        space = self._settings.space_id

        while asyncio.get_event_loop().time() < deadline:
            try:
                resp = await self._client.get(
                    f"/api/{space}/deployments/{deployment_id}",
                )
                resp.raise_for_status()
                data = resp.json()
                task_id = data.get("TaskId")

                if task_id:
                    task_resp = await self._client.get(
                        f"/api/tasks/{task_id}",
                    )
                    task_resp.raise_for_status()
                    task = task_resp.json()

                    if task.get("IsCompleted"):
                        state = task.get("State", "Unknown")
                        return DeploymentResult(
                            success=state == "Success",
                            deployment_id=deployment_id,
                            status=state,
                            error_message=task.get(
                                "ErrorMessage",
                                "",
                            ),
                        )
            except httpx.HTTPError:
                log.exception("deployment.poll_failed")

            await asyncio.sleep(self._poll_interval)

        return DeploymentResult(
            success=False,
            deployment_id=deployment_id,
            status="TimedOut",
        )

    async def close(self) -> None:
        await self._client.aclose()
