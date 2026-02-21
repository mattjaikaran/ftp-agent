from __future__ import annotations

from datetime import UTC, timedelta

from ftp_agent.models.file_entry import FileEntry, MigrationStatus
from ftp_agent.models.report import MigrationReport
from ftp_agent.models.results import BatchResult


class TestMigrationStatus:
    def test_enum_values(self) -> None:
        assert MigrationStatus.PENDING == 0
        assert MigrationStatus.IN_PROGRESS == 1
        assert MigrationStatus.SUCCESS == 2
        assert MigrationStatus.FAILED == 3
        assert MigrationStatus.RETRY_PENDING == 4

    def test_enum_is_int(self) -> None:
        assert isinstance(MigrationStatus.PENDING, int)

    def test_enum_member_count(self) -> None:
        assert len(MigrationStatus) == 5


class TestFileEntry:
    def test_defaults(self) -> None:
        entry = FileEntry(id="f1", name="test.xml", legacy_config="<old/>")
        assert entry.id == "f1"
        assert entry.name == "test.xml"
        assert entry.legacy_config == "<old/>"
        assert entry.new_config == ""
        assert entry.status == MigrationStatus.PENDING
        assert entry.retry_count == 0
        assert entry.last_error == ""
        assert entry.commit_hash == ""
        assert entry.deployment_id == ""
        assert entry.source_path == ""
        assert entry.destination_path == ""
        assert entry.protocol == ""

    def test_created_at_is_utc(self) -> None:
        entry = FileEntry(id="f1", name="test.xml", legacy_config="<old/>")
        assert entry.created_at.tzinfo == UTC

    def test_updated_at_is_utc(self) -> None:
        entry = FileEntry(id="f1", name="test.xml", legacy_config="<old/>")
        assert entry.updated_at.tzinfo == UTC

    def test_custom_status(self) -> None:
        entry = FileEntry(
            id="f2",
            name="other.xml",
            legacy_config="<cfg/>",
            status=MigrationStatus.FAILED,
            retry_count=2,
            last_error="connection refused",
        )
        assert entry.status == MigrationStatus.FAILED
        assert entry.retry_count == 2
        assert entry.last_error == "connection refused"


class TestBatchResult:
    def _make_entry(self, id_: str) -> FileEntry:
        return FileEntry(id=id_, name=f"{id_}.xml", legacy_config="<cfg/>")

    def test_total_processed_empty(self) -> None:
        result = BatchResult(batch_number=1)
        assert result.total_processed == 0

    def test_total_processed_with_entries(self) -> None:
        result = BatchResult(
            batch_number=1,
            succeeded=[self._make_entry("s1"), self._make_entry("s2")],
            failed=[self._make_entry("f1")],
            retrying=[self._make_entry("r1")],
        )
        assert result.total_processed == 4

    def test_all_succeeded_true(self) -> None:
        result = BatchResult(
            batch_number=1,
            succeeded=[self._make_entry("s1")],
        )
        assert result.all_succeeded is True

    def test_all_succeeded_false_with_failed(self) -> None:
        result = BatchResult(
            batch_number=1,
            succeeded=[self._make_entry("s1")],
            failed=[self._make_entry("f1")],
        )
        assert result.all_succeeded is False

    def test_all_succeeded_false_with_retrying(self) -> None:
        result = BatchResult(
            batch_number=1,
            succeeded=[self._make_entry("s1")],
            retrying=[self._make_entry("r1")],
        )
        assert result.all_succeeded is False

    def test_all_succeeded_empty_batch(self) -> None:
        result = BatchResult(batch_number=1)
        assert result.all_succeeded is True

    def test_defaults(self) -> None:
        result = BatchResult(batch_number=5)
        assert result.batch_number == 5
        assert result.succeeded == []
        assert result.failed == []
        assert result.retrying == []
        assert result.duration == timedelta()
        assert result.commit_hash == ""
        assert result.deployment_id == ""


class TestMigrationReport:
    def test_success_rate_zero_files(self) -> None:
        report = MigrationReport(total_files=0)
        assert report.success_rate == 0.0

    def test_success_rate_all_succeeded(self) -> None:
        report = MigrationReport(total_files=10, succeeded=10)
        assert report.success_rate == 100.0

    def test_success_rate_partial(self) -> None:
        report = MigrationReport(total_files=10, succeeded=7)
        assert report.success_rate == 70.0

    def test_to_summary_basic_format(self) -> None:
        report = MigrationReport(
            total_files=5,
            succeeded=3,
            failed=1,
            pending=1,
            in_progress=0,
            retry_pending=0,
        )
        summary = report.to_summary()
        assert "Migration Report" in summary
        assert "Total files: 5" in summary
        assert "Succeeded:   3" in summary
        assert "Failed:      1" in summary
        assert "Pending:     1" in summary
        assert "In Progress: 0" in summary
        assert "Retry Pending: 0" in summary
        assert "Success Rate:  60.0%" in summary
        assert "Duration:" in summary

    def test_to_summary_includes_failed_entries(self) -> None:
        failed_entry = FileEntry(
            id="abc123",
            name="broken.xml",
            legacy_config="<old/>",
            status=MigrationStatus.FAILED,
            last_error="timeout exceeded",
        )
        report = MigrationReport(
            total_files=1,
            failed=1,
            failed_entries=[failed_entry],
        )
        summary = report.to_summary()
        assert "Failed Entries:" in summary
        assert "broken.xml" in summary
        assert "abc123" in summary
        assert "timeout exceeded" in summary

    def test_to_summary_no_failed_entries_section(self) -> None:
        report = MigrationReport(total_files=1, succeeded=1)
        summary = report.to_summary()
        assert "Failed Entries:" not in summary

    def test_generated_at_is_utc(self) -> None:
        report = MigrationReport()
        assert report.generated_at.tzinfo == UTC
