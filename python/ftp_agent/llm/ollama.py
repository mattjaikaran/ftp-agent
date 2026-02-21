from __future__ import annotations

import httpx
import structlog

from ftp_agent.config.settings import OllamaSettings
from ftp_agent.llm.protocol import LLMMessage, LLMResponse, LLMUsage

log = structlog.get_logger()


class OllamaProvider:
    """Ollama provider using the native Ollama API (not OpenAI-compat).

    Supports model management operations in addition to chat.
    """

    def __init__(self, settings: OllamaSettings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._settings.model

    async def chat(self, messages: list[LLMMessage]) -> LLMResponse:
        payload = {
            "model": self._settings.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        log.debug("ollama.chat.request", model=self._settings.model, msg_count=len(messages))

        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        message = data.get("message", {})
        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)

        result = LLMResponse(
            content=message.get("content", ""),
            model=data.get("model", self._settings.model),
            finish_reason=data.get("done_reason", ""),
            usage=LLMUsage(
                prompt_tokens=prompt_eval_count,
                completion_tokens=eval_count,
                total_tokens=prompt_eval_count + eval_count,
            ),
        )
        log.debug("ollama.chat.response", tokens=result.usage.total_tokens)
        return result

    async def health(self) -> bool:
        """Check if Ollama is running by hitting the root endpoint."""
        try:
            resp = await self._client.get("/")
            return resp.status_code == 200
        except (httpx.HTTPError, ConnectionError, OSError):
            log.warning("ollama.health.failed")
            return False

    async def list_models(self) -> list[str]:
        """List all locally available models."""
        resp = await self._client.get("/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]

    async def pull_model(self, name: str) -> None:
        """Pull a model from the Ollama registry."""
        log.info("ollama.pull_model", model=name)
        resp = await self._client.post(
            "/api/pull",
            json={"name": name, "stream": False},
            timeout=600,
        )
        resp.raise_for_status()
        log.info("ollama.pull_model.done", model=name)

    async def delete_model(self, name: str) -> None:
        """Delete a locally available model."""
        log.info("ollama.delete_model", model=name)
        resp = await self._client.request(
            "DELETE",
            "/api/delete",
            json={"name": name},
        )
        resp.raise_for_status()
        log.info("ollama.delete_model.done", model=name)

    async def close(self) -> None:
        await self._client.aclose()
