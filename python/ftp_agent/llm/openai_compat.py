from __future__ import annotations

import httpx
import structlog

from ftp_agent.config.settings import OpenAICompatSettings
from ftp_agent.llm.protocol import LLMMessage, LLMResponse, LLMUsage

log = structlog.get_logger()


class OpenAICompatProvider:
    """Generic OpenAI-compatible provider.

    Works with vLLM, llama.cpp, LocalAI, LM Studio, Together, Groq,
    or any endpoint that speaks the OpenAI chat completions format.
    """

    def __init__(self, settings: OpenAICompatSettings) -> None:
        self._settings = settings
        headers: dict[str, str] = {}
        api_key = settings.api_key.get_secret_value()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            base_url=settings.base_url,
            headers=headers,
            timeout=settings.timeout_seconds,
        )

    @property
    def provider_name(self) -> str:
        return "openai-compat"

    @property
    def model_name(self) -> str:
        return self._settings.model

    async def chat(self, messages: list[LLMMessage]) -> LLMResponse:
        payload = {
            "model": self._settings.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        log.debug(
            "openai_compat.chat.request",
            model=self._settings.model,
            base_url=self._settings.base_url,
            msg_count=len(messages),
        )

        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        result = LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", self._settings.model),
            finish_reason=choice.get("finish_reason", ""),
            usage=LLMUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
        )
        log.debug("openai_compat.chat.response", tokens=result.usage.total_tokens)
        return result

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/models")
            return resp.status_code == 200
        except httpx.HTTPError:
            log.warning("openai_compat.health.failed")
            return False

    async def close(self) -> None:
        await self._client.aclose()
