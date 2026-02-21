from __future__ import annotations

import json
from pathlib import Path

import structlog

from ftp_agent.models.file_entry import FileEntry

log = structlog.get_logger()


class ConfigWriter:
    """Write translated JSON configs to the target directory."""

    def __init__(self, target_dir: str = "configs") -> None:
        self._target_dir = Path(target_dir)

    async def write_config(self, entry: FileEntry) -> str:
        """Write the new config JSON to disk.

        Returns the absolute path of the written file.
        Raises ValueError if `entry.new_config` is empty.
        """
        if not entry.new_config:
            msg = f"No new config to write for entry {entry.id}"
            raise ValueError(msg)

        self._target_dir.mkdir(parents=True, exist_ok=True)

        safe_name = self._safe_filename(entry)
        file_path = self._target_dir / safe_name

        # Pretty-print valid JSON; write raw if it fails to parse
        try:
            parsed = json.loads(entry.new_config)
            content = json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            content = entry.new_config

        file_path.write_text(content + "\n", encoding="utf-8")

        log.info("config_writer.written", entry_id=entry.id, path=str(file_path))
        return str(file_path)

    @staticmethod
    def _safe_filename(entry: FileEntry) -> str:
        """Generate a safe filename from entry metadata.

        Format: {protocol}-{sanitized_name}-{id}.json
        """
        parts: list[str] = []
        if entry.protocol:
            parts.append(entry.protocol.lower())

        # Sanitize name: keep only alphanumeric and hyphens
        name = entry.name.lower()
        name = "".join(c if c.isalnum() or c == "-" else "-" for c in name)
        # Collapse consecutive hyphens and strip leading/trailing
        while "--" in name:
            name = name.replace("--", "-")
        name = name.strip("-")
        if name:
            parts.append(name)

        parts.append(entry.id)
        return "-".join(parts) + ".json"
