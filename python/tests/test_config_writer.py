from __future__ import annotations

import json
from pathlib import Path

import pytest

from ftp_agent.models.file_entry import FileEntry
from ftp_agent.translation.config_writer import ConfigWriter


def _make_entry(
    entry_id: str = "f1",
    name: str = "test-feed",
    protocol: str = "SFTP",
    new_config: str = '{"name": "test"}',
) -> FileEntry:
    return FileEntry(
        id=entry_id,
        name=name,
        legacy_config="host=example.com",
        new_config=new_config,
        protocol=protocol,
    )


class TestSafeFilename:
    def test_basic_filename(self) -> None:
        entry = _make_entry(entry_id="abc", name="daily-feed", protocol="SFTP")
        result = ConfigWriter._safe_filename(entry)
        assert result == "sftp-daily-feed-abc.json"

    def test_special_characters_sanitized(self) -> None:
        entry = _make_entry(entry_id="x1", name="My Feed (v2)", protocol="FTP")
        result = ConfigWriter._safe_filename(entry)
        assert result == "ftp-my-feed-v2-x1.json"
        # No spaces, parens, or consecutive hyphens
        assert "  " not in result
        assert "()" not in result

    def test_no_protocol(self) -> None:
        entry = _make_entry(entry_id="z9", name="orphan", protocol="")
        result = ConfigWriter._safe_filename(entry)
        assert result == "orphan-z9.json"

    def test_empty_name(self) -> None:
        entry = _make_entry(entry_id="n1", name="", protocol="SFTP")
        result = ConfigWriter._safe_filename(entry)
        assert result == "sftp-n1.json"

    def test_consecutive_hyphens_collapsed(self) -> None:
        entry = _make_entry(entry_id="h1", name="a---b", protocol="")
        result = ConfigWriter._safe_filename(entry)
        assert result == "a-b-h1.json"


class TestWriteConfig:
    async def test_creates_file_with_correct_content(self, tmp_path: Path) -> None:
        writer = ConfigWriter(target_dir=str(tmp_path / "output"))
        entry = _make_entry(new_config='{"protocol": "SFTP", "host": "sftp.example.com"}')

        path = await writer.write_config(entry)

        written = Path(path)
        assert written.exists()
        content = written.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert parsed["protocol"] == "SFTP"
        assert parsed["host"] == "sftp.example.com"

    async def test_pretty_prints_json(self, tmp_path: Path) -> None:
        writer = ConfigWriter(target_dir=str(tmp_path / "output"))
        entry = _make_entry(new_config='{"a":1,"b":2}')

        path = await writer.write_config(entry)

        content = Path(path).read_text(encoding="utf-8")
        # Pretty-printed JSON has newlines and indentation
        assert "  " in content
        assert content.endswith("\n")
        # Verify it's still valid JSON
        parsed = json.loads(content)
        assert parsed == {"a": 1, "b": 2}

    async def test_raises_on_empty_new_config(self, tmp_path: Path) -> None:
        writer = ConfigWriter(target_dir=str(tmp_path / "output"))
        entry = _make_entry(new_config="")

        with pytest.raises(ValueError, match="No new config to write"):
            await writer.write_config(entry)

    async def test_creates_target_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested" / "dir"
        writer = ConfigWriter(target_dir=str(nested))
        entry = _make_entry()

        path = await writer.write_config(entry)

        assert nested.exists()
        assert Path(path).exists()

    async def test_writes_raw_content_on_invalid_json(self, tmp_path: Path) -> None:
        """If new_config is not valid JSON, write it raw instead of crashing."""
        writer = ConfigWriter(target_dir=str(tmp_path / "output"))
        entry = _make_entry(new_config="not valid json but truthy")

        path = await writer.write_config(entry)

        content = Path(path).read_text(encoding="utf-8")
        assert "not valid json but truthy" in content

    async def test_filename_matches_entry_metadata(self, tmp_path: Path) -> None:
        writer = ConfigWriter(target_dir=str(tmp_path))
        entry = _make_entry(entry_id="abc", name="my-feed", protocol="SFTP")

        path = await writer.write_config(entry)

        assert Path(path).name == "sftp-my-feed-abc.json"
