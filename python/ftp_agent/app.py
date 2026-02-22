"""Application container with explicit dependency wiring."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from ftp_agent.ci.github_actions import GitHubActionsMonitor
from ftp_agent.ci.protocol import CIMonitor
from ftp_agent.ci.stub import StubCIMonitor
from ftp_agent.config.settings import (
    AppSettings,
    DeploymentProviderType,
    MonitoringProviderType,
)
from ftp_agent.deployment.octopus import OctopusDeployClient
from ftp_agent.deployment.protocol import DeploymentClient
from ftp_agent.deployment.stub import StubDeploymentClient
from ftp_agent.diagnostics.engine import DiagnosticEngine
from ftp_agent.git.manager import GitManager
from ftp_agent.llm.factory import create_llm_provider
from ftp_agent.llm.protocol import LLMProvider
from ftp_agent.monitoring.datadog import DatadogClient
from ftp_agent.monitoring.protocol import MonitoringClient
from ftp_agent.monitoring.stub import StubMonitoringClient
from ftp_agent.orchestration.batch import BatchOrchestrator
from ftp_agent.state.store import StateStore
from ftp_agent.translation.config_writer import ConfigWriter
from ftp_agent.translation.legacy_parser import LegacyConfigParser
from ftp_agent.translation.translator import ConfigTranslator

log = structlog.get_logger()


@dataclass
class App:
    """Central application container — every dependency is explicitly wired."""

    settings: AppSettings
    llm: LLMProvider
    state_store: StateStore
    parser: LegacyConfigParser
    translator: ConfigTranslator
    config_writer: ConfigWriter
    git_manager: GitManager
    ci_monitor: CIMonitor
    deployment_client: DeploymentClient
    monitoring_client: MonitoringClient
    diagnostic_engine: DiagnosticEngine
    orchestrator: BatchOrchestrator
    dry_run: bool = False
    _closables: list[object] = field(default_factory=list, repr=False)

    async def close(self) -> None:
        for obj in self._closables:
            if hasattr(obj, "close"):
                await obj.close()
            elif hasattr(obj, "aclose"):
                await obj.aclose()


def create_app(settings: AppSettings | None = None, *, dry_run: bool = False) -> App:
    """Factory that wires all dependencies from settings."""
    if settings is None:
        settings = AppSettings()

    # LLM
    llm = create_llm_provider(settings.llm)
    closables: list[object] = []
    if hasattr(llm, "close"):
        closables.append(llm)

    # State
    state_store = StateStore(settings.agent.state_database_path)

    # Translation
    parser = LegacyConfigParser()
    translator = ConfigTranslator(
        llm=llm,
        prompt_path=settings.config_translation_prompt_path,
    )
    config_writer = ConfigWriter(
        target_dir=settings.github.target_repo_path + "/configs"
        if settings.github.target_repo_path
        else "configs",
    )

    # Git
    git_manager = GitManager(
        repo_path=settings.github.target_repo_path or ".",
    )

    # CI
    ci_monitor: CIMonitor
    if dry_run or not settings.github.repository:
        ci_monitor = StubCIMonitor()
    else:
        ci_monitor = GitHubActionsMonitor(
            github=settings.github,
            agent=settings.agent,
        )

    # Deployment
    deployment_client: DeploymentClient
    if dry_run or settings.deployment.provider == DeploymentProviderType.STUB:
        deployment_client = StubDeploymentClient()
    else:
        client = OctopusDeployClient(
            settings=settings.deployment.octopus,
            agent=settings.agent,
        )
        closables.append(client)
        deployment_client = client

    # Monitoring
    monitoring_client: MonitoringClient
    if dry_run or settings.monitoring.provider == MonitoringProviderType.STUB:
        monitoring_client = StubMonitoringClient()
    else:
        dd_client = DatadogClient(
            settings=settings.monitoring.datadog,
            agent=settings.agent,
        )
        closables.append(dd_client)
        monitoring_client = dd_client

    # Diagnostics
    diagnostic_engine = DiagnosticEngine(
        llm=llm,
        prompt_path=settings.error_diagnosis_prompt_path,
    )

    # Orchestrator
    orchestrator = BatchOrchestrator(
        settings=settings.agent,
        state_store=state_store,
        parser=parser,
        translator=translator,
        config_writer=config_writer,
        git_manager=git_manager,
        ci_monitor=ci_monitor,
        deployment_client=deployment_client,
        monitoring_client=monitoring_client,
        diagnostic_engine=diagnostic_engine,
    )

    return App(
        settings=settings,
        llm=llm,
        state_store=state_store,
        parser=parser,
        translator=translator,
        config_writer=config_writer,
        git_manager=git_manager,
        ci_monitor=ci_monitor,
        deployment_client=deployment_client,
        monitoring_client=monitoring_client,
        diagnostic_engine=diagnostic_engine,
        orchestrator=orchestrator,
        dry_run=dry_run,
        _closables=closables,
    )
