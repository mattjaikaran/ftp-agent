from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ftp_agent.llm.protocol import LLMResponse, LLMUsage
from ftp_agent.models.file_entry import FileEntry
from ftp_agent.translation.translator import ConfigTranslator


def _make_entry(entry_id: str = "f1", legacy_config: str = "host=sftp.example.com") -> FileEntry:
    return FileEntry(id=entry_id, name="test-feed", legacy_config=legacy_config)


def _make_mock_llm(content: str) -> AsyncMock:
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = LLMResponse(
        content=content,
        usage=LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        model="test-model",
        finish_reason="stop",
    )
    return mock_llm


class TestExtractJSON:
    def test_json_fenced_block(self) -> None:
        text = 'Some preamble\n```json\n{"name": "test", "port": 22}\n```\nMore text'
        result = ConfigTranslator._extract_json(text)
        assert result == '{"name": "test", "port": 22}'

    def test_plain_fenced_block(self) -> None:
        text = 'Here is the config:\n```\n{"host": "sftp.example.com"}\n```'
        result = ConfigTranslator._extract_json(text)
        assert result == '{"host": "sftp.example.com"}'

    def test_raw_json(self) -> None:
        text = 'The translated config is {"protocol": "SFTP", "port": 22} as requested.'
        result = ConfigTranslator._extract_json(text)
        assert result == '{"protocol": "SFTP", "port": 22}'

    def test_no_json_returns_empty(self) -> None:
        text = "I could not translate this config. Please provide more details."
        result = ConfigTranslator._extract_json(text)
        assert result == ""

    def test_invalid_json_in_fences_falls_through(self) -> None:
        text = '```json\n{invalid json here}\n```\nBut here is {"valid": true} inline.'
        result = ConfigTranslator._extract_json(text)
        assert result == '{"valid": true}'

    def test_nested_json(self) -> None:
        text = '```json\n{"server": {"host": "a.com", "port": 22}}\n```'
        result = ConfigTranslator._extract_json(text)
        assert '"server"' in result
        assert '"host"' in result

    def test_json_fenced_preferred_over_raw(self) -> None:
        """When both fenced and raw JSON exist, fenced should be returned."""
        text = 'Raw: {"raw": true}\n```json\n{"fenced": true}\n```'
        result = ConfigTranslator._extract_json(text)
        assert result == '{"fenced": true}'


class TestTranslate:
    async def test_translate_returns_json(self) -> None:
        mock_llm = _make_mock_llm('```json\n{"name": "test", "protocol": "SFTP"}\n```')
        translator = ConfigTranslator(llm=mock_llm)
        entry = _make_entry()

        result = await translator.translate(entry)

        assert '"name"' in result
        assert '"SFTP"' in result
        mock_llm.chat.assert_awaited_once()

    async def test_translate_raises_on_no_json(self) -> None:
        mock_llm = _make_mock_llm("Sorry, I cannot translate this config.")
        translator = ConfigTranslator(llm=mock_llm)
        entry = _make_entry()

        with pytest.raises(ValueError, match="did not contain valid JSON"):
            await translator.translate(entry)

    async def test_translate_passes_legacy_config_to_prompt(self) -> None:
        mock_llm = _make_mock_llm('```json\n{"ok": true}\n```')
        translator = ConfigTranslator(llm=mock_llm)
        entry = _make_entry(legacy_config="host=custom.example.com\nport=2222")

        await translator.translate(entry)

        # Verify the LLM was called with a message containing the legacy config
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        user_msg = [m for m in messages if m.role == "user"][0]
        assert "custom.example.com" in user_msg.content
        assert "2222" in user_msg.content

    async def test_translate_uses_custom_prompt(self, tmp_path: Path) -> None:
        """Custom prompt path is loaded and used."""
        prompt_dir = tmp_path
        prompt_file = prompt_dir / "custom-prompt.md"
        prompt_file.write_text(
            "Custom prompt: translate {{LEGACY_CONFIG}} to JSON.",
            encoding="utf-8",
        )

        mock_llm = _make_mock_llm('```json\n{"custom": true}\n```')
        translator = ConfigTranslator(llm=mock_llm, prompt_path=str(prompt_file))
        entry = _make_entry()

        result = await translator.translate(entry)
        assert '"custom"' in result

        # Check that the custom prompt was actually used
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        user_msg = [m for m in messages if m.role == "user"][0]
        assert "Custom prompt:" in user_msg.content
