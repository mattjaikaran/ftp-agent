from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from ftp_agent.models.file_entry import FileEntry


@dataclass
class BatchResult:
    batch_number: int
    succeeded: list[FileEntry] = field(default_factory=list)
    failed: list[FileEntry] = field(default_factory=list)
    retrying: list[FileEntry] = field(default_factory=list)
    duration: timedelta = field(default_factory=timedelta)
    commit_hash: str = ""
    deployment_id: str = ""

    @property
    def total_processed(self) -> int:
        return len(self.succeeded) + len(self.failed) + len(self.retrying)

    @property
    def all_succeeded(self) -> bool:
        return not self.failed and not self.retrying


@dataclass
class BuildResult:
    success: bool
    run_id: str = ""
    conclusion: str = ""
    log_output: str = ""
    url: str = ""


@dataclass
class DeploymentResult:
    success: bool
    deployment_id: str = ""
    status: str = ""
    error_message: str = ""


@dataclass
class LogQueryResult:
    has_errors: bool = False
    total_log_entries: int = 0
    error_count: int = 0
    warning_count: int = 0
    error_messages: list[str] = field(default_factory=list)
    warning_messages: list[str] = field(default_factory=list)
    file_processed_successfully: bool = False


@dataclass
class DiagnosticResult:
    analysis: str = ""
    suggested_changes: list[str] = field(default_factory=list)
    revised_config: str = ""
    is_recoverable: bool = False
    root_cause: str = ""
