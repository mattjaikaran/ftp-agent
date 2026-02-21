from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class LLMMessage:
    """A single message in a chat conversation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMUsage:
    """Token usage statistics from an LLM response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """Structured response from an LLM provider."""

    content: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    model: str = ""
    finish_reason: str = ""


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol that all LLM providers must satisfy."""

    async def chat(self, messages: list[LLMMessage]) -> LLMResponse: ...

    async def health(self) -> bool: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...
