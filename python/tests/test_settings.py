from __future__ import annotations

from ftp_agent.config.settings import (
    AppSettings,
    DeploymentProviderType,
    LLMProviderType,
    MonitoringProviderType,
)


class TestAppSettingsDefaults:
    def test_instantiation(self) -> None:
        settings = AppSettings()
        assert settings is not None

    def test_agent_defaults(self) -> None:
        settings = AppSettings()
        assert settings.agent.batch_size == 10
        assert settings.agent.max_retries_per_file == 3
        assert settings.agent.ci_build_timeout_minutes == 20
        assert settings.agent.deploy_wait_timeout_minutes == 30
        assert settings.agent.stop_on_batch_failure is False
        assert settings.agent.state_database_path == "migration-state.db"

    def test_github_defaults(self) -> None:
        settings = AppSettings()
        assert settings.github.base_branch == "main"
        assert settings.github.repository == ""

    def test_llm_defaults(self) -> None:
        settings = AppSettings()
        assert settings.llm.provider == LLMProviderType.MINIMAX
        assert settings.llm.minimax.model == "MiniMax-M2.5"
        assert settings.llm.anthropic.model == "claude-sonnet-4-20250514"
        assert settings.llm.openai_compat.model == "gpt-4o"
        assert settings.llm.ollama.model == "llama3.3"

    def test_deployment_defaults(self) -> None:
        settings = AppSettings()
        assert settings.deployment.provider == DeploymentProviderType.STUB
        assert settings.deployment.octopus.space_id == "Spaces-1"

    def test_monitoring_defaults(self) -> None:
        settings = AppSettings()
        assert settings.monitoring.provider == MonitoringProviderType.STUB
        assert settings.monitoring.datadog.api_url == "https://api.datadoghq.com"

    def test_prompt_path_defaults(self) -> None:
        settings = AppSettings()
        assert settings.config_translation_prompt_path == "prompts/config-translation.md"
        assert settings.error_diagnosis_prompt_path == "prompts/error-diagnosis.md"


class TestLLMProviderType:
    def test_values(self) -> None:
        assert LLMProviderType.MINIMAX.value == "minimax"
        assert LLMProviderType.ANTHROPIC.value == "anthropic"
        assert LLMProviderType.OPENAI_COMPAT.value == "openai-compat"
        assert LLMProviderType.OLLAMA.value == "ollama"

    def test_member_count(self) -> None:
        assert len(LLMProviderType) == 4

    def test_string_subclass(self) -> None:
        assert isinstance(LLMProviderType.MINIMAX, str)


class TestDeploymentProviderType:
    def test_values(self) -> None:
        assert DeploymentProviderType.OCTOPUS.value == "octopus"
        assert DeploymentProviderType.STUB.value == "stub"

    def test_member_count(self) -> None:
        assert len(DeploymentProviderType) == 2


class TestMonitoringProviderType:
    def test_values(self) -> None:
        assert MonitoringProviderType.DATADOG.value == "datadog"
        assert MonitoringProviderType.STUB.value == "stub"

    def test_member_count(self) -> None:
        assert len(MonitoringProviderType) == 2


class TestEnvVarOverrides:
    def test_override_agent_batch_size(self, monkeypatch: object) -> None:
        monkeypatch.setenv("FTPAGENT_AGENT__BATCH_SIZE", "25")  # type: ignore[attr-defined]
        settings = AppSettings()
        assert settings.agent.batch_size == 25

    def test_override_llm_provider(self, monkeypatch: object) -> None:
        monkeypatch.setenv("FTPAGENT_LLM__PROVIDER", "anthropic")  # type: ignore[attr-defined]
        settings = AppSettings()
        assert settings.llm.provider == LLMProviderType.ANTHROPIC

    def test_override_deployment_provider(self, monkeypatch: object) -> None:
        monkeypatch.setenv("FTPAGENT_DEPLOYMENT__PROVIDER", "octopus")  # type: ignore[attr-defined]
        settings = AppSettings()
        assert settings.deployment.provider == DeploymentProviderType.OCTOPUS

    def test_override_github_repository(self, monkeypatch: object) -> None:
        monkeypatch.setenv("FTPAGENT_GITHUB__REPOSITORY", "org/repo")  # type: ignore[attr-defined]
        settings = AppSettings()
        assert settings.github.repository == "org/repo"

    def test_override_monitoring_provider(self, monkeypatch: object) -> None:
        monkeypatch.setenv("FTPAGENT_MONITORING__PROVIDER", "datadog")  # type: ignore[attr-defined]
        settings = AppSettings()
        assert settings.monitoring.provider == MonitoringProviderType.DATADOG

    def test_override_nested_llm_minimax_model(self, monkeypatch: object) -> None:
        monkeypatch.setenv("FTPAGENT_LLM__MINIMAX__MODEL", "custom-model")  # type: ignore[attr-defined]
        settings = AppSettings()
        assert settings.llm.minimax.model == "custom-model"
