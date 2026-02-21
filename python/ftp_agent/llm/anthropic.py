from __future__ import annotations

from typing import Any

import structlog

from ftp_agent.config.settings import AnthropicSettings
from ftp_agent.llm.protocol import LLMMessage, LLMResponse, LLMUsage

log = structlog.get_logger()


class AnthropicProvider:
    """Claude provider using the anthropic SDK.

    Separates system messages per Anthropic API requirements: system content
    is passed as a top-level kwarg, not in the messages list.
    """

    def __init__(self, settings: AnthropicSettings) -> None:
        try:
            import anthropic
        except ImportError as e:
            msg = (
                "anthropic package not installed. "
                "Install with: uv pip install 'ftp-agent[anthropic]'"
            )
            raise ImportError(msg) from e

        self._settings = settings
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.api_key.get_secret_value(),
        )

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._settings.model

    async def chat(self, messages: list[LLMMessage]) -> LLMResponse:
        system_msg = ""
        chat_messages: list[dict[str, str]] = []

        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                chat_messages.append({"role": m.role, "content": m.content})

        kwargs: dict[str, Any] = {
            "model": self._settings.model,
            "max_tokens": 4096,
            "messages": chat_messages,
        }
        if system_msg:
            kwargs["system"] = system_msg

        log.debug(
            "anthropic.chat.request",
            model=self._settings.model,
            msg_count=len(chat_messages),
            has_system=bool(system_msg),
        )

        resp = await self._client.messages.create(**kwargs)
        content = resp.content[0].text if resp.content else ""

        result = LLMResponse(
            content=content,
            model=resp.model,
            finish_reason=resp.stop_reason or "",
            usage=LLMUsage(
                prompt_tokens=resp.usage.input_tokens,
                completion_tokens=resp.usage.output_tokens,
                total_tokens=resp.usage.input_tokens + resp.usage.output_tokens,
            ),
        )
        log.debug("anthropic.chat.response", tokens=result.usage.total_tokens)
        return result

    async def health(self) -> bool:
        return bool(self._settings.api_key.get_secret_value())

    async def close(self) -> None:
        await self._client.close()
