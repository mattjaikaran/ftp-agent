from __future__ import annotations

from ftp_agent.config.settings import LLMProviderType, LLMSettings
from ftp_agent.llm.protocol import LLMProvider


def create_llm_provider(settings: LLMSettings) -> LLMProvider:
    """Create an LLM provider instance based on the configured provider type.

    Uses lazy imports to avoid loading unused provider dependencies.
    """
    match settings.provider:
        case LLMProviderType.MINIMAX:
            from ftp_agent.llm.minimax import MiniMaxProvider

            return MiniMaxProvider(settings.minimax)
        case LLMProviderType.ANTHROPIC:
            from ftp_agent.llm.anthropic import AnthropicProvider

            return AnthropicProvider(settings.anthropic)
        case LLMProviderType.OPENAI_COMPAT:
            from ftp_agent.llm.openai_compat import OpenAICompatProvider

            return OpenAICompatProvider(settings.openai_compat)
        case LLMProviderType.OLLAMA:
            from ftp_agent.llm.ollama import OllamaProvider

            return OllamaProvider(settings.ollama)
        case _:
            msg = f"Unknown LLM provider: {settings.provider}"
            raise ValueError(msg)
