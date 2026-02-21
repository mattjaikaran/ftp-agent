from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from ftp_agent.models.file_entry import FileEntry
from ftp_agent.models.results import BatchResult


@dataclass
class MigrationReport:
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    total_files: int = 0
    succeeded: int = 0
    failed: int = 0
    pending: int = 0
    in_progress: int = 0
    retry_pending: int = 0
    total_duration: timedelta = field(default_factory=timedelta)
    failed_entries: list[FileEntry] = field(default_factory=list)
    batch_results: list[BatchResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.succeeded / self.total_files) * 100

    def to_summary(self) -> str:
        lines = [
            f"Migration Report — {self.generated_at:%Y-%m-%d %H:%M:%S UTC}",
            f"Total files: {self.total_files}",
            f"Succeeded:   {self.succeeded}",
            f"Failed:      {self.failed}",
            f"Pending:     {self.pending}",
            f"In Progress: {self.in_progress}",
            f"Retry Pending: {self.retry_pending}",
            f"Success Rate:  {self.success_rate:.1f}%",
            f"Duration:      {self.total_duration}",
        ]
        if self.failed_entries:
            lines.append("\nFailed Entries:")
            for entry in self.failed_entries:
                lines.append(f"  - {entry.name} ({entry.id}): {entry.last_error}")
        return "\n".join(lines)
