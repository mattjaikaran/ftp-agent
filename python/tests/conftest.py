"""Shared test fixtures."""

from __future__ import annotations

import pytest

from ftp_agent.config.settings import AppSettings
from ftp_agent.models.file_entry import FileEntry
from ftp_agent.state.store import StateStore


@pytest.fixture
async def store(tmp_path):
    """Provide a fresh StateStore backed by a temporary database."""
    db_path = str(tmp_path / "test.db")
    async with StateStore(db_path) as s:
        yield s


@pytest.fixture
def sample_entries() -> list[FileEntry]:
    """Three sample FileEntry objects for testing."""
    return [
        FileEntry(
            id="f1",
            name="daily-sales",
            legacy_config="host=sftp.vendor.com\nport=22",
            protocol="SFTP",
        ),
        FileEntry(
            id="f2",
            name="invoice-emails",
            legacy_config="host=mail.company.com\nfolder=Inbox",
            protocol="Exchange",
        ),
        FileEntry(
            id="f3",
            name="hourly-feed",
            legacy_config="host=ftp.partner.net\nport=21",
            protocol="FTP",
        ),
    ]


@pytest.fixture
def settings() -> AppSettings:
    """Default AppSettings for tests."""
    return AppSettings()
