from __future__ import annotations

import enum
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderType(str, enum.Enum):
    MINIMAX = "minimax"
    ANTHROPIC = "anthropic"
    OPENAI_COMPAT = "openai-compat"
    OLLAMA = "ollama"


class DeploymentProviderType(str, enum.Enum):
    OCTOPUS = "octopus"
    STUB = "stub"


class MonitoringProviderType(str, enum.Enum):
    DATADOG = "datadog"
    STUB = "stub"


class AgentSettings(BaseSettings):
    batch_size: int = 10
    max_retries_per_file: int = 3
    ci_build_timeout_minutes: int = 20
    deploy_wait_timeout_minutes: int = 30
    datadog_check_delay_minutes: int = 5
    log_query_window_minutes: int = 15
    poll_interval_seconds: int = 30
    stop_on_batch_failure: bool = False
    max_batches_per_run: int = 0
    legacy_config_source_path: str = ""
    state_database_path: str = "migration-state.db"
    schedule_interval_hours: float = 0


class GitHubSettings(BaseSettings):
    repository: str = ""
    base_branch: str = "main"
    workflow_name: str = ""
    target_repo_path: str = ""


class MiniMaxSettings(BaseSettings):
    base_url: str = "https://api.minimax.io/v1"
    model: str = "MiniMax-M2.5"
    api_key: SecretStr = SecretStr("")
    timeout_seconds: int = 120


class AnthropicSettings(BaseSettings):
    model: str = "claude-sonnet-4-20250514"
    api_key: SecretStr = SecretStr("")
    timeout_seconds: int = 120


class OpenAICompatSettings(BaseSettings):
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    api_key: SecretStr = SecretStr("")
    timeout_seconds: int = 120


class OllamaSettings(BaseSettings):
    base_url: str = "http://localhost:11434"
    model: str = "llama3.3"
    timeout_seconds: int = 120


class LLMSettings(BaseSettings):
    provider: LLMProviderType = LLMProviderType.MINIMAX
    minimax: MiniMaxSettings = MiniMaxSettings()
    anthropic: AnthropicSettings = AnthropicSettings()
    openai_compat: OpenAICompatSettings = OpenAICompatSettings()
    ollama: OllamaSettings = OllamaSettings()


class OctopusSettings(BaseSettings):
    server_url: str = ""
    api_key: SecretStr = SecretStr("")
    project_name: str = ""
    environment_name: str = ""
    space_id: str = "Spaces-1"


class DeploymentSettings(BaseSettings):
    provider: DeploymentProviderType = DeploymentProviderType.STUB
    octopus: OctopusSettings = OctopusSettings()


class DatadogSettings(BaseSettings):
    api_url: str = "https://api.datadoghq.com"
    api_key: SecretStr = SecretStr("")
    app_key: SecretStr = SecretStr("")
    service_name: str = ""
    environment: str = ""


class MonitoringSettings(BaseSettings):
    provider: MonitoringProviderType = MonitoringProviderType.STUB
    datadog: DatadogSettings = DatadogSettings()


_TOML_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "settings.toml"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FTPAGENT_",
        env_nested_delimiter="__",
        case_sensitive=False,
        toml_file=str(_TOML_PATH) if _TOML_PATH.exists() else None,
    )

    agent: AgentSettings = AgentSettings()
    github: GitHubSettings = GitHubSettings()
    llm: LLMSettings = LLMSettings()
    deployment: DeploymentSettings = DeploymentSettings()
    monitoring: MonitoringSettings = MonitoringSettings()

    config_translation_prompt_path: str = "prompts/config-translation.md"
    error_diagnosis_prompt_path: str = "prompts/error-diagnosis.md"
