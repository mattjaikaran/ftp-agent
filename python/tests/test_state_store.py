from __future__ import annotations

from pathlib import Path

import pytest

from ftp_agent.models.file_entry import FileEntry, MigrationStatus
from ftp_agent.state.store import StateStore


def _make_entry(
    id_: str,
    name: str = "",
    status: MigrationStatus = MigrationStatus.PENDING,
    *,
    legacy_config: str = "<cfg/>",
    source_path: str = "/src",
    destination_path: str = "/dst",
    protocol: str = "sftp",
) -> FileEntry:
    return FileEntry(
        id=id_,
        name=name or f"{id_}.xml",
        legacy_config=legacy_config,
        status=status,
        source_path=source_path,
        destination_path=destination_path,
        protocol=protocol,
    )


@pytest.fixture
async def store(tmp_path: Path) -> StateStore:
    db_path = str(tmp_path / "test.db")
    async with StateStore(db_path) as s:
        yield s  # type: ignore[misc]


# ── Schema / lifecycle ─────────────────────────────────────────────


class TestInitialize:
    async def test_creates_table(self, store: StateStore) -> None:
        cursor = await store.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='file_entries'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["name"] == "file_entries"

    async def test_creates_status_index(self, store: StateStore) -> None:
        cursor = await store.db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_file_entries_status'"
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_db_property_raises_when_not_initialized(self, tmp_path: Path) -> None:
        s = StateStore(str(tmp_path / "unused.db"))
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = s.db


# ── load_entries ───────────────────────────────────────────────────


class TestLoadEntries:
    async def test_inserts_entries(self, store: StateStore) -> None:
        entries = [_make_entry("a"), _make_entry("b")]
        inserted = await store.load_entries(entries)
        assert inserted == 2

        all_entries = await store.get_all_entries()
        assert len(all_entries) == 2

    async def test_skips_duplicates(self, store: StateStore) -> None:
        entries = [_make_entry("a")]
        await store.load_entries(entries)
        inserted = await store.load_entries(entries)
        assert inserted == 0

        all_entries = await store.get_all_entries()
        assert len(all_entries) == 1

    async def test_mixed_new_and_duplicate(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        inserted = await store.load_entries([_make_entry("a"), _make_entry("b")])
        assert inserted == 1

        all_entries = await store.get_all_entries()
        assert len(all_entries) == 2

    async def test_preserves_fields(self, store: StateStore) -> None:
        entry = _make_entry(
            "x",
            name="special.xml",
            legacy_config="<legacy/>",
            source_path="/in",
            destination_path="/out",
            protocol="ftps",
        )
        await store.load_entries([entry])

        loaded = await store.get_entry("x")
        assert loaded is not None
        assert loaded.name == "special.xml"
        assert loaded.legacy_config == "<legacy/>"
        assert loaded.source_path == "/in"
        assert loaded.destination_path == "/out"
        assert loaded.protocol == "ftps"


# ── has_pending_files ──────────────────────────────────────────────


class TestHasPendingFiles:
    async def test_false_when_empty(self, store: StateStore) -> None:
        assert await store.has_pending_files() is False

    async def test_true_with_pending(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a", status=MigrationStatus.PENDING)])
        assert await store.has_pending_files() is True

    async def test_true_with_retry_pending(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a", status=MigrationStatus.RETRY_PENDING)])
        assert await store.has_pending_files() is True

    async def test_false_when_all_completed(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a", status=MigrationStatus.SUCCESS)])
        assert await store.has_pending_files() is False

    async def test_false_when_all_failed(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a", status=MigrationStatus.FAILED)])
        assert await store.has_pending_files() is False


# ── get_next_batch ─────────────────────────────────────────────────


class TestGetNextBatch:
    async def test_empty_table(self, store: StateStore) -> None:
        batch = await store.get_next_batch(5)
        assert batch == []

    async def test_respects_size_limit(self, store: StateStore) -> None:
        entries = [_make_entry(f"e{i}") for i in range(10)]
        await store.load_entries(entries)
        batch = await store.get_next_batch(3)
        assert len(batch) == 3

    async def test_returns_all_when_fewer_than_limit(self, store: StateStore) -> None:
        entries = [_make_entry(f"e{i}") for i in range(2)]
        await store.load_entries(entries)
        batch = await store.get_next_batch(10)
        assert len(batch) == 2

    async def test_prioritizes_retry_over_pending(self, store: StateStore) -> None:
        await store.load_entries(
            [
                _make_entry("pending1", status=MigrationStatus.PENDING),
                _make_entry("pending2", status=MigrationStatus.PENDING),
            ]
        )
        # Mark one as retry
        await store.increment_retry("pending1", "transient error")

        batch = await store.get_next_batch(10)
        assert len(batch) == 2
        # RETRY_PENDING should come first
        assert batch[0].id == "pending1"
        assert batch[0].status == MigrationStatus.RETRY_PENDING
        assert batch[1].id == "pending2"
        assert batch[1].status == MigrationStatus.PENDING

    async def test_excludes_completed_statuses(self, store: StateStore) -> None:
        await store.load_entries(
            [
                _make_entry("s", status=MigrationStatus.SUCCESS),
                _make_entry("f", status=MigrationStatus.FAILED),
                _make_entry("ip", status=MigrationStatus.IN_PROGRESS),
                _make_entry("p", status=MigrationStatus.PENDING),
            ]
        )
        batch = await store.get_next_batch(10)
        assert len(batch) == 1
        assert batch[0].id == "p"


# ── Status transitions ────────────────────────────────────────────


class TestStatusTransitions:
    async def test_mark_in_progress(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        await store.mark_in_progress("a")

        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.status == MigrationStatus.IN_PROGRESS

    async def test_mark_success(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        await store.mark_success("a")

        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.status == MigrationStatus.SUCCESS

    async def test_mark_failed(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        await store.mark_failed("a", "connection timeout")

        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.status == MigrationStatus.FAILED
        assert entry.last_error == "connection timeout"

    async def test_mark_failed_preserves_other_fields(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a", name="myfile.xml")])
        await store.mark_failed("a", "oops")

        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.name == "myfile.xml"
        assert entry.status == MigrationStatus.FAILED


# ── increment_retry ───────────────────────────────────────────────


class TestIncrementRetry:
    async def test_increments_count(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        await store.increment_retry("a", "first error")
        await store.increment_retry("a", "second error")

        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.retry_count == 2

    async def test_sets_retry_pending_status(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        await store.increment_retry("a", "transient")

        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.status == MigrationStatus.RETRY_PENDING

    async def test_records_last_error(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        await store.increment_retry("a", "first error")
        await store.increment_retry("a", "second error")

        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.last_error == "second error"


# ── update_new_config ──────────────────────────────────────────────


class TestUpdateNewConfig:
    async def test_stores_config(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        await store.update_new_config("a", '{"new": "config"}')

        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.new_config == '{"new": "config"}'

    async def test_overwrites_previous(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        await store.update_new_config("a", "v1")
        await store.update_new_config("a", "v2")

        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.new_config == "v2"


# ── update_commit_hash / update_deployment_id ──────────────────────


class TestFieldUpdates:
    async def test_update_commit_hash(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        await store.update_commit_hash("a", "abc123")

        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.commit_hash == "abc123"

    async def test_update_deployment_id(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        await store.update_deployment_id("a", "deploy-42")

        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.deployment_id == "deploy-42"


# ── get_entry ──────────────────────────────────────────────────────


class TestGetEntry:
    async def test_returns_entry(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a")])
        entry = await store.get_entry("a")
        assert entry is not None
        assert entry.id == "a"

    async def test_returns_none_for_missing(self, store: StateStore) -> None:
        entry = await store.get_entry("nonexistent")
        assert entry is None


# ── get_entries_by_status ──────────────────────────────────────────


class TestGetEntriesByStatus:
    async def test_filters_by_status(self, store: StateStore) -> None:
        await store.load_entries(
            [
                _make_entry("a", status=MigrationStatus.PENDING),
                _make_entry("b", status=MigrationStatus.SUCCESS),
                _make_entry("c", status=MigrationStatus.PENDING),
            ]
        )
        pending = await store.get_entries_by_status(MigrationStatus.PENDING)
        assert len(pending) == 2
        assert {e.id for e in pending} == {"a", "c"}

    async def test_returns_empty_for_no_matches(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("a", status=MigrationStatus.PENDING)])
        failed = await store.get_entries_by_status(MigrationStatus.FAILED)
        assert failed == []


# ── generate_report ────────────────────────────────────────────────


class TestGenerateReport:
    async def test_empty_db(self, store: StateStore) -> None:
        report = await store.generate_report()
        assert report.total_files == 0
        assert report.succeeded == 0
        assert report.failed == 0
        assert report.pending == 0
        assert report.in_progress == 0
        assert report.retry_pending == 0
        assert report.failed_entries == []

    async def test_counts_by_status(self, store: StateStore) -> None:
        await store.load_entries(
            [
                _make_entry("p1", status=MigrationStatus.PENDING),
                _make_entry("p2", status=MigrationStatus.PENDING),
                _make_entry("s1", status=MigrationStatus.SUCCESS),
                _make_entry("f1", status=MigrationStatus.FAILED),
                _make_entry("ip1", status=MigrationStatus.IN_PROGRESS),
                _make_entry("r1", status=MigrationStatus.RETRY_PENDING),
            ]
        )
        report = await store.generate_report()
        assert report.total_files == 6
        assert report.pending == 2
        assert report.succeeded == 1
        assert report.failed == 1
        assert report.in_progress == 1
        assert report.retry_pending == 1

    async def test_includes_failed_entries(self, store: StateStore) -> None:
        await store.load_entries([_make_entry("f1", status=MigrationStatus.FAILED)])
        await store.mark_failed("f1", "bad config")

        report = await store.generate_report()
        assert len(report.failed_entries) == 1
        assert report.failed_entries[0].id == "f1"
        assert report.failed_entries[0].last_error == "bad config"

    async def test_success_rate(self, store: StateStore) -> None:
        await store.load_entries(
            [
                _make_entry("s1", status=MigrationStatus.SUCCESS),
                _make_entry("s2", status=MigrationStatus.SUCCESS),
                _make_entry("f1", status=MigrationStatus.FAILED),
                _make_entry("p1", status=MigrationStatus.PENDING),
            ]
        )
        report = await store.generate_report()
        assert report.success_rate == 50.0
