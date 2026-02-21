from __future__ import annotations

from typing import Protocol, runtime_checkable

from ftp_agent.models.results import DeploymentResult


@runtime_checkable
class DeploymentClient(Protocol):
    """Protocol for deployment trigger/wait services."""

    async def trigger_deployment(
        self,
        version: str,
        environment: str,
    ) -> DeploymentResult: ...

    async def wait_for_deployment(
        self,
        deployment_id: str,
        timeout_seconds: float = 1800,
    ) -> DeploymentResult: ...
