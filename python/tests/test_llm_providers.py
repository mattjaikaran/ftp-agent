"""Tests for LLM provider implementations."""

from __future__ import annotations

import pytest
import respx
from httpx import Response
from pydantic import SecretStr

from ftp_agent.config.settings import (
    LLMProviderType,
    LLMSettings,
    MiniMaxSettings,
    OllamaSettings,
    OpenAICompatSettings,
)
from ftp_agent.llm.factory import create_llm_provider
from ftp_agent.llm.minimax import MiniMaxProvider
from ftp_agent.llm.ollama import OllamaProvider
from ftp_agent.llm.openai_compat import OpenAICompatProvider
from ftp_agent.llm.protocol import LLMMessage, LLMProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

OPENAI_CHAT_RESPONSE = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "model": "test-model",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello from the LLM!"},
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    },
}

OLLAMA_CHAT_RESPONSE = {
    "model": "llama3.3",
    "message": {"role": "assistant", "content": "Hello from Ollama!"},
    "done": True,
    "done_reason": "stop",
    "eval_count": 20,
    "prompt_eval_count": 8,
}

OLLAMA_TAGS_RESPONSE = {
    "models": [
        {"name": "llama3.3:latest", "size": 4_000_000_000},
        {"name": "mistral:latest", "size": 3_500_000_000},
    ]
}


@pytest.fixture
def minimax_settings() -> MiniMaxSettings:
    return MiniMaxSettings(
        base_url="https://api.minimax.io/v1",
        model="MiniMax-M2.5",
        api_key=SecretStr("test-key"),
        timeout_seconds=30,
    )


@pytest.fixture
def openai_compat_settings() -> OpenAICompatSettings:
    return OpenAICompatSettings(
        base_url="https://api.together.xyz/v1",
        model="meta-llama/Llama-3-8b-chat",
        api_key=SecretStr("test-key"),
        timeout_seconds=30,
    )


@pytest.fixture
def ollama_settings() -> OllamaSettings:
    return OllamaSettings(
        base_url="http://localhost:11434",
        model="llama3.3",
        timeout_seconds=30,
    )


# ---------------------------------------------------------------------------
# MiniMax provider tests
# ---------------------------------------------------------------------------


@respx.mock
async def test_minimax_chat(minimax_settings: MiniMaxSettings) -> None:
    respx.post("https://api.minimax.io/v1/chat/completions").mock(
        return_value=Response(200, json=OPENAI_CHAT_RESPONSE)
    )

    provider = MiniMaxProvider(minimax_settings)
    messages = [LLMMessage(role="user", content="Hi")]
    result = await provider.chat(messages)

    assert result.content == "Hello from the LLM!"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5
    assert result.usage.total_tokens == 15
    assert result.finish_reason == "stop"
    assert result.model == "test-model"

    await provider.close()


@respx.mock
async def test_minimax_health_success(minimax_settings: MiniMaxSettings) -> None:
    respx.get("https://api.minimax.io/v1/models").mock(
        return_value=Response(200, json={"data": []})
    )

    provider = MiniMaxProvider(minimax_settings)
    assert await provider.health() is True
    await provider.close()


@respx.mock
async def test_minimax_health_failure(minimax_settings: MiniMaxSettings) -> None:
    respx.get("https://api.minimax.io/v1/models").mock(return_value=Response(500))

    provider = MiniMaxProvider(minimax_settings)
    assert await provider.health() is False
    await provider.close()


def test_minimax_properties(minimax_settings: MiniMaxSettings) -> None:
    provider = MiniMaxProvider(minimax_settings)
    assert provider.provider_name == "minimax"
    assert provider.model_name == "MiniMax-M2.5"


# ---------------------------------------------------------------------------
# OpenAI-compatible provider tests
# ---------------------------------------------------------------------------


@respx.mock
async def test_openai_compat_chat(openai_compat_settings: OpenAICompatSettings) -> None:
    respx.post("https://api.together.xyz/v1/chat/completions").mock(
        return_value=Response(200, json=OPENAI_CHAT_RESPONSE)
    )

    provider = OpenAICompatProvider(openai_compat_settings)
    messages = [LLMMessage(role="user", content="Hi")]
    result = await provider.chat(messages)

    assert result.content == "Hello from the LLM!"
    assert result.usage.total_tokens == 15
    assert result.finish_reason == "stop"

    await provider.close()


@respx.mock
async def test_openai_compat_health_success(
    openai_compat_settings: OpenAICompatSettings,
) -> None:
    respx.get("https://api.together.xyz/v1/models").mock(
        return_value=Response(200, json={"data": []})
    )

    provider = OpenAICompatProvider(openai_compat_settings)
    assert await provider.health() is True
    await provider.close()


def test_openai_compat_properties(openai_compat_settings: OpenAICompatSettings) -> None:
    provider = OpenAICompatProvider(openai_compat_settings)
    assert provider.provider_name == "openai-compat"
    assert provider.model_name == "meta-llama/Llama-3-8b-chat"


@respx.mock
async def test_openai_compat_no_api_key() -> None:
    """Provider should work without an API key (e.g. local vLLM)."""
    settings = OpenAICompatSettings(
        base_url="http://localhost:8000/v1",
        model="local-model",
        api_key=SecretStr(""),
        timeout_seconds=10,
    )
    respx.post("http://localhost:8000/v1/chat/completions").mock(
        return_value=Response(200, json=OPENAI_CHAT_RESPONSE)
    )

    provider = OpenAICompatProvider(settings)
    result = await provider.chat([LLMMessage(role="user", content="Hi")])
    assert result.content == "Hello from the LLM!"
    await provider.close()


# ---------------------------------------------------------------------------
# Ollama provider tests
# ---------------------------------------------------------------------------


@respx.mock
async def test_ollama_chat(ollama_settings: OllamaSettings) -> None:
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=Response(200, json=OLLAMA_CHAT_RESPONSE)
    )

    provider = OllamaProvider(ollama_settings)
    messages = [LLMMessage(role="user", content="Hi")]
    result = await provider.chat(messages)

    assert result.content == "Hello from Ollama!"
    assert result.usage.prompt_tokens == 8
    assert result.usage.completion_tokens == 20
    assert result.usage.total_tokens == 28
    assert result.finish_reason == "stop"
    assert result.model == "llama3.3"

    await provider.close()


@respx.mock
async def test_ollama_list_models(ollama_settings: OllamaSettings) -> None:
    respx.get("http://localhost:11434/api/tags").mock(
        return_value=Response(200, json=OLLAMA_TAGS_RESPONSE)
    )

    provider = OllamaProvider(ollama_settings)
    models = await provider.list_models()

    assert models == ["llama3.3:latest", "mistral:latest"]
    await provider.close()


@respx.mock
async def test_ollama_health_success(ollama_settings: OllamaSettings) -> None:
    respx.get("http://localhost:11434/").mock(return_value=Response(200, text="Ollama is running"))

    provider = OllamaProvider(ollama_settings)
    assert await provider.health() is True
    await provider.close()


@respx.mock
async def test_ollama_health_failure(ollama_settings: OllamaSettings) -> None:
    respx.get("http://localhost:11434/").mock(side_effect=ConnectionError)

    provider = OllamaProvider(ollama_settings)
    assert await provider.health() is False
    await provider.close()


def test_ollama_properties(ollama_settings: OllamaSettings) -> None:
    provider = OllamaProvider(ollama_settings)
    assert provider.provider_name == "ollama"
    assert provider.model_name == "llama3.3"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_minimax_satisfies_protocol(minimax_settings: MiniMaxSettings) -> None:
    provider = MiniMaxProvider(minimax_settings)
    assert isinstance(provider, LLMProvider)


def test_openai_compat_satisfies_protocol(
    openai_compat_settings: OpenAICompatSettings,
) -> None:
    provider = OpenAICompatProvider(openai_compat_settings)
    assert isinstance(provider, LLMProvider)


def test_ollama_satisfies_protocol(ollama_settings: OllamaSettings) -> None:
    provider = OllamaProvider(ollama_settings)
    assert isinstance(provider, LLMProvider)


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


def test_factory_creates_minimax() -> None:
    settings = LLMSettings(
        provider=LLMProviderType.MINIMAX,
        minimax=MiniMaxSettings(api_key=SecretStr("test-key")),
    )
    provider = create_llm_provider(settings)
    assert isinstance(provider, MiniMaxProvider)
    assert provider.provider_name == "minimax"


def test_factory_creates_openai_compat() -> None:
    settings = LLMSettings(
        provider=LLMProviderType.OPENAI_COMPAT,
        openai_compat=OpenAICompatSettings(api_key=SecretStr("test-key")),
    )
    provider = create_llm_provider(settings)
    assert isinstance(provider, OpenAICompatProvider)
    assert provider.provider_name == "openai-compat"


def test_factory_creates_ollama() -> None:
    settings = LLMSettings(
        provider=LLMProviderType.OLLAMA,
        ollama=OllamaSettings(),
    )
    provider = create_llm_provider(settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.provider_name == "ollama"


def test_factory_unknown_provider() -> None:
    settings = LLMSettings(provider=LLMProviderType.MINIMAX)
    # Monkey-patch to simulate unknown provider
    settings.provider = "nonexistent"  # type: ignore[assignment]
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_llm_provider(settings)
