from __future__ import annotations

from datetime import UTC, datetime

import aiosqlite
import structlog

from ftp_agent.models.file_entry import FileEntry, MigrationStatus
from ftp_agent.models.report import MigrationReport

log = structlog.get_logger()


class StateStore:
    """Async SQLite-backed state store for migration file tracking.

    Usage::

        async with StateStore("migration-state.db") as store:
            await store.load_entries(entries)
            batch = await store.get_next_batch(10)
    """

    def __init__(self, db_path: str = "migration-state.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open DB connection and create schema."""
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS file_entries (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                legacy_config TEXT NOT NULL,
                new_config TEXT DEFAULT '',
                status INTEGER NOT NULL DEFAULT 0,
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                commit_hash TEXT DEFAULT '',
                deployment_id TEXT DEFAULT '',
                source_path TEXT DEFAULT '',
                destination_path TEXT DEFAULT '',
                protocol TEXT DEFAULT ''
            )
        """)
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_entries_status ON file_entries(status)"
        )
        await self._db.commit()
        log.info("state_store.initialized", db_path=self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def __aenter__(self) -> StateStore:
        await self.initialize()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    @property
    def db(self) -> aiosqlite.Connection:
        """Return the active database connection or raise if not initialized."""
        if self._db is None:
            raise RuntimeError("StateStore not initialized. Call initialize() first.")
        return self._db

    # ── Bulk load ──────────────────────────────────────────────────────

    async def load_entries(self, entries: list[FileEntry]) -> int:
        """Bulk insert entries. Skips existing IDs. Returns count inserted."""
        inserted = 0
        for entry in entries:
            try:
                cursor = await self.db.execute(
                    """INSERT OR IGNORE INTO file_entries
                    (id, name, legacy_config, new_config, status, retry_count,
                     last_error, source_path, destination_path, protocol)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry.id,
                        entry.name,
                        entry.legacy_config,
                        entry.new_config,
                        entry.status.value,
                        entry.retry_count,
                        entry.last_error,
                        entry.source_path,
                        entry.destination_path,
                        entry.protocol,
                    ),
                )
                if cursor.rowcount and cursor.rowcount > 0:
                    inserted += 1
            except Exception:
                log.exception("state_store.load_entry_failed", entry_id=entry.id)
        await self.db.commit()
        log.info("state_store.loaded_entries", count=inserted, total=len(entries))
        return inserted

    # ── Query helpers ──────────────────────────────────────────────────

    async def has_pending_files(self) -> bool:
        """Return True if any PENDING or RETRY_PENDING entries exist."""
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM file_entries WHERE status IN (?, ?)",
            (MigrationStatus.PENDING.value, MigrationStatus.RETRY_PENDING.value),
        )
        row = await cursor.fetchone()
        return bool(row and row[0] > 0)

    async def get_next_batch(self, size: int) -> list[FileEntry]:
        """Get next batch, prioritizing RETRY_PENDING over PENDING."""
        cursor = await self.db.execute(
            """SELECT * FROM file_entries
            WHERE status IN (?, ?)
            ORDER BY
                CASE status WHEN ? THEN 0 ELSE 1 END,
                created_at ASC
            LIMIT ?""",
            (
                MigrationStatus.PENDING.value,
                MigrationStatus.RETRY_PENDING.value,
                MigrationStatus.RETRY_PENDING.value,
                size,
            ),
        )
        rows = await cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]

    async def get_entry(self, entry_id: str) -> FileEntry | None:
        """Fetch a single entry by ID, or None if not found."""
        cursor = await self.db.execute("SELECT * FROM file_entries WHERE id = ?", (entry_id,))
        row = await cursor.fetchone()
        return self._row_to_entry(row) if row else None

    async def get_all_entries(self) -> list[FileEntry]:
        """Return all entries ordered by creation time."""
        cursor = await self.db.execute("SELECT * FROM file_entries ORDER BY created_at")
        rows = await cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]

    async def get_entries_by_status(self, status: MigrationStatus) -> list[FileEntry]:
        """Return all entries matching the given status."""
        cursor = await self.db.execute(
            "SELECT * FROM file_entries WHERE status = ? ORDER BY created_at",
            (status.value,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]

    # ── Status transitions ─────────────────────────────────────────────

    async def mark_in_progress(self, entry_id: str) -> None:
        """Set entry status to IN_PROGRESS."""
        await self._update_status(entry_id, MigrationStatus.IN_PROGRESS)

    async def mark_success(self, entry_id: str) -> None:
        """Set entry status to SUCCESS."""
        await self._update_status(entry_id, MigrationStatus.SUCCESS)

    async def mark_failed(self, entry_id: str, error: str) -> None:
        """Set entry status to FAILED with an error message."""
        await self.db.execute(
            """UPDATE file_entries SET status = ?, last_error = ?,
            updated_at = datetime('now') WHERE id = ?""",
            (MigrationStatus.FAILED.value, error, entry_id),
        )
        await self.db.commit()

    async def increment_retry(self, entry_id: str, error: str) -> None:
        """Bump retry count, set RETRY_PENDING, record the error."""
        await self.db.execute(
            """UPDATE file_entries SET status = ?, retry_count = retry_count + 1,
            last_error = ?, updated_at = datetime('now') WHERE id = ?""",
            (MigrationStatus.RETRY_PENDING.value, error, entry_id),
        )
        await self.db.commit()

    # ── Field updates ──────────────────────────────────────────────────

    async def update_new_config(self, entry_id: str, new_config: str) -> None:
        """Store the translated configuration."""
        await self.db.execute(
            "UPDATE file_entries SET new_config = ?, updated_at = datetime('now') WHERE id = ?",
            (new_config, entry_id),
        )
        await self.db.commit()

    async def update_commit_hash(self, entry_id: str, commit_hash: str) -> None:
        """Record the git commit hash for this entry."""
        await self.db.execute(
            "UPDATE file_entries SET commit_hash = ?, updated_at = datetime('now') WHERE id = ?",
            (commit_hash, entry_id),
        )
        await self.db.commit()

    async def update_deployment_id(self, entry_id: str, deployment_id: str) -> None:
        """Record the deployment ID for this entry."""
        await self.db.execute(
            """UPDATE file_entries SET deployment_id = ?,
            updated_at = datetime('now') WHERE id = ?""",
            (deployment_id, entry_id),
        )
        await self.db.commit()

    # ── Reporting ──────────────────────────────────────────────────────

    async def generate_report(self) -> MigrationReport:
        """Aggregate status counts and build a MigrationReport."""
        counts: dict[int, int] = {}
        cursor = await self.db.execute(
            "SELECT status, COUNT(*) as cnt FROM file_entries GROUP BY status"
        )
        for row in await cursor.fetchall():
            counts[row["status"]] = row["cnt"]

        failed_entries = await self.get_entries_by_status(MigrationStatus.FAILED)
        total = sum(counts.values())

        return MigrationReport(
            total_files=total,
            succeeded=counts.get(MigrationStatus.SUCCESS.value, 0),
            failed=counts.get(MigrationStatus.FAILED.value, 0),
            pending=counts.get(MigrationStatus.PENDING.value, 0),
            in_progress=counts.get(MigrationStatus.IN_PROGRESS.value, 0),
            retry_pending=counts.get(MigrationStatus.RETRY_PENDING.value, 0),
            failed_entries=failed_entries,
        )

    # ── Internal helpers ───────────────────────────────────────────────

    async def _update_status(self, entry_id: str, status: MigrationStatus) -> None:
        await self.db.execute(
            "UPDATE file_entries SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status.value, entry_id),
        )
        await self.db.commit()

    @staticmethod
    def _row_to_entry(row: aiosqlite.Row) -> FileEntry:
        return FileEntry(
            id=row["id"],
            name=row["name"],
            legacy_config=row["legacy_config"],
            new_config=row["new_config"] or "",
            status=MigrationStatus(row["status"]),
            retry_count=row["retry_count"],
            last_error=row["last_error"] or "",
            created_at=(
                datetime.fromisoformat(row["created_at"]).replace(tzinfo=UTC)
                if row["created_at"]
                else datetime.now(UTC)
            ),
            updated_at=(
                datetime.fromisoformat(row["updated_at"]).replace(tzinfo=UTC)
                if row["updated_at"]
                else datetime.now(UTC)
            ),
            commit_hash=row["commit_hash"] or "",
            deployment_id=row["deployment_id"] or "",
            source_path=row["source_path"] or "",
            destination_path=row["destination_path"] or "",
            protocol=row["protocol"] or "",
        )
