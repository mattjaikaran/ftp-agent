from __future__ import annotations

import csv
import uuid
from pathlib import Path

import structlog

from ftp_agent.models.file_entry import FileEntry

log = structlog.get_logger()


class LegacyConfigParser:
    """Parse legacy config files (CSV, text key=value, INI) into FileEntry objects."""

    def parse_csv(self, path: str | Path) -> list[FileEntry]:
        """Parse a CSV file where each row is a file ingestion config."""
        path = Path(path)
        if not path.exists():
            log.warning("legacy_parser.file_not_found", path=str(path))
            return []

        entries: list[FileEntry] = []
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entry = self._row_to_entry(row)
                if entry:
                    entries.append(entry)

        log.info("legacy_parser.parsed_csv", path=str(path), count=len(entries))
        return entries

    def parse_text(self, content: str, source_path: str = "") -> FileEntry:
        """Parse a single key=value text config into a FileEntry."""
        props: dict[str, str] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                props[key.strip().lower()] = value.strip()

        entry_id = props.get("id", str(uuid.uuid4())[:8])
        name = props.get("name", source_path or entry_id)
        protocol = props.get("type", props.get("protocol", "SFTP")).upper()

        return FileEntry(
            id=entry_id,
            name=name,
            legacy_config=content,
            source_path=source_path,
            protocol=protocol,
        )

    def parse_ini(self, content: str, source_path: str = "") -> list[FileEntry]:
        """Parse an INI-style config. Each [section] becomes a separate FileEntry."""
        entries: list[FileEntry] = []
        current_section: str | None = None
        section_lines: list[str] = []
        preamble_lines: list[str] = []

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                # Flush previous section
                if current_section is not None:
                    block = "\n".join(section_lines)
                    entries.append(self.parse_text(block, source_path=source_path))
                current_section = stripped[1:-1]
                section_lines = [f"name={current_section}"]
            elif current_section is not None:
                section_lines.append(line)
            else:
                preamble_lines.append(line)

        # Flush last section
        if current_section is not None and section_lines:
            block = "\n".join(section_lines)
            entries.append(self.parse_text(block, source_path=source_path))

        # If no sections found, treat entire content as a single text config
        if not entries:
            entries.append(self.parse_text(content, source_path=source_path))

        log.info("legacy_parser.parsed_ini", path=source_path, count=len(entries))
        return entries

    def parse_directory(self, path: str | Path) -> list[FileEntry]:
        """Parse all .cfg/.txt/.ini/.conf files in a directory."""
        path = Path(path)
        entries: list[FileEntry] = []
        for f in sorted(path.iterdir()):
            if f.suffix in (".cfg", ".txt", ".ini", ".conf"):
                content = f.read_text(encoding="utf-8-sig")
                if f.suffix == ".ini":
                    entries.extend(self.parse_ini(content, source_path=str(f)))
                else:
                    entries.append(self.parse_text(content, source_path=str(f)))
        log.info("legacy_parser.parsed_directory", path=str(path), count=len(entries))
        return entries

    def _row_to_entry(self, row: dict[str, str]) -> FileEntry | None:
        """Convert a CSV row dict to a FileEntry."""
        # Normalize keys to lowercase, skip empty values
        row = {k.strip().lower(): v.strip() for k, v in row.items() if v}
        if not row:
            return None

        entry_id = row.get("id", str(uuid.uuid4())[:8])
        name = row.get("name", entry_id)
        protocol = row.get("type", row.get("protocol", "SFTP")).upper()

        # Rebuild the original config as key=value text for LLM consumption
        legacy_lines = [f"{k}={v}" for k, v in sorted(row.items())]
        legacy_config = "\n".join(legacy_lines)

        return FileEntry(
            id=entry_id,
            name=name,
            legacy_config=legacy_config,
            source_path=row.get("source_path", ""),
            destination_path=row.get("destination_path", ""),
            protocol=protocol,
        )
