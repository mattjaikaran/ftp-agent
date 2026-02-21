from __future__ import annotations

import json
import re
from pathlib import Path

import structlog

from ftp_agent.llm.protocol import LLMMessage, LLMProvider
from ftp_agent.models.file_entry import FileEntry

log = structlog.get_logger()

FALLBACK_PROMPT = """\
You are a configuration migration specialist. \
Translate this legacy file ingestion config to the new JSON format.

Legacy config:
```
{{LEGACY_CONFIG}}
```

Return ONLY valid JSON wrapped in ```json code fences."""


class ConfigTranslator:
    """Translate legacy configs to new JSON format via an LLM provider."""

    def __init__(
        self,
        llm: LLMProvider,
        prompt_path: str = "prompts/config-translation.md",
    ) -> None:
        self._llm = llm
        self._prompt_path = prompt_path
        self._prompt_template: str | None = None

    def _load_prompt(self) -> str:
        """Load prompt template from file, falling back to built-in."""
        if self._prompt_template is not None:
            return self._prompt_template

        path = Path(self._prompt_path)
        if path.exists():
            self._prompt_template = path.read_text(encoding="utf-8")
            log.info("translator.loaded_prompt", path=str(path))
        else:
            self._prompt_template = FALLBACK_PROMPT
            log.warning("translator.using_fallback_prompt", path=str(path))
        return self._prompt_template

    async def translate(self, entry: FileEntry) -> str:
        """Translate a legacy config to new JSON format via LLM.

        Returns the extracted JSON string, or raises ValueError if the
        LLM response does not contain valid JSON.
        """
        prompt = self._load_prompt().replace("{{LEGACY_CONFIG}}", entry.legacy_config)

        messages = [
            LLMMessage(role="system", content="You are a configuration migration specialist."),
            LLMMessage(role="user", content=prompt),
        ]

        log.info("translator.calling_llm", entry_id=entry.id, entry_name=entry.name)
        response = await self._llm.chat(messages)

        config_json = self._extract_json(response.content)
        if not config_json:
            msg = f"LLM response did not contain valid JSON for entry {entry.id}"
            raise ValueError(msg)

        log.info(
            "translator.success",
            entry_id=entry.id,
            tokens=response.usage.total_tokens,
        )
        return config_json

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from markdown code fences or raw text.

        Tries in order:
        1. ```json ... ``` fenced blocks
        2. ``` ... ``` fenced blocks (no language tag)
        3. Raw JSON (first { to last })

        Returns the extracted JSON string, or "" if none found.
        """
        # Try ```json ... ``` first
        match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Try ``` ... ``` (no language tag)
        match = re.search(r"```\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Try raw JSON — find all { ... } spans and check each
        for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text):
            candidate = match.group(0).strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue

        return ""
