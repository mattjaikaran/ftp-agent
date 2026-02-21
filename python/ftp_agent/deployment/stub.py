from __future__ import annotations

import asyncio

import structlog

from ftp_agent.models.results import DeploymentResult

log = structlog.get_logger()

_counter = 0


class StubDeploymentClient:
    """No-op deployment client that always reports success."""

    async def trigger_deployment(
        self,
        version: str,
        environment: str,
    ) -> DeploymentResult:
        global _counter
        _counter += 1
        deployment_id = f"stub-deploy-{_counter}"
        log.info(
            "deployment.stub.triggered",
            deployment_id=deployment_id,
            version=version,
        )
        return DeploymentResult(
            success=True,
            deployment_id=deployment_id,
            status="Queued",
        )

    async def wait_for_deployment(
        self,
        deployment_id: str,
        timeout_seconds: float = 1800,
    ) -> DeploymentResult:
        log.info("deployment.stub.waiting", deployment_id=deployment_id)
        await asyncio.sleep(0.1)
        return DeploymentResult(
            success=True,
            deployment_id=deployment_id,
            status="Success",
        )
