from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime


class MigrationStatus(enum.IntEnum):
    PENDING = 0
    IN_PROGRESS = 1
    SUCCESS = 2
    FAILED = 3
    RETRY_PENDING = 4


@dataclass
class FileEntry:
    id: str
    name: str
    legacy_config: str
    new_config: str = ""
    status: MigrationStatus = MigrationStatus.PENDING
    retry_count: int = 0
    last_error: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    commit_hash: str = ""
    deployment_id: str = ""
    source_path: str = ""
    destination_path: str = ""
    protocol: str = ""
