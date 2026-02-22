"""Tests for FastAPI server endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import ftp_agent.server as server_module
from ftp_agent.models.file_entry import FileEntry, MigrationStatus
from ftp_agent.server import api_router


@pytest.fixture
async def mock_app(tmp_path):
    """Create a mock app instance with a real state store backed by tmp DB."""
    from ftp_agent.state.store import StateStore

    store = StateStore(str(tmp_path / "test.db"))
    await store.initialize()

    app = AsyncMock()
    app.state_store = store
    app.settings = AsyncMock()
    app.settings.agent.batch_size = 10
    app.settings.agent.max_retries_per_file = 3
    app.settings.agent.poll_interval_seconds = 30
    app.settings.llm.provider.value = "minimax"
    app.settings.deployment.provider.value = "stub"
    app.settings.monitoring.provider.value = "stub"
    app.llm.provider_name = "minimax"
    app.llm.model_name = "MiniMax-M2.5"
    app.llm.health = AsyncMock(return_value=True)

    original = server_module._app_instance
    server_module._app_instance = app

    yield app

    server_module._app_instance = original
    await store.close()


@pytest.fixture
async def client(mock_app):
    """Create a test client with the mock app instance injected."""
    app = FastAPI()
    app.include_router(api_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- Existing tests ---


async def test_health(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


async def test_status(client: AsyncClient):
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_files" in data
    assert "success_rate" in data


async def test_entries_list(client: AsyncClient):
    resp = await client.get("/api/entries")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert "total" in data


async def test_entry_not_found(client: AsyncClient):
    resp = await client.get("/api/entries/nonexistent")
    assert resp.status_code == 404


async def test_report(client: AsyncClient):
    resp = await client.get("/api/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data


async def test_config_summary(client: AsyncClient):
    resp = await client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "agent" in data
    assert "llm" in data


# --- New tests ---


async def test_csv_export(client: AsyncClient, mock_app):
    """GET /api/report/csv returns CSV content-type with proper headers."""
    # Load a sample entry so the CSV has data
    entry = FileEntry(
        id="csv1",
        name="sftp-export-test",
        legacy_config="host=old.example.com",
        protocol="SFTP",
    )
    await mock_app.state_store.load_entries([entry])

    resp = await client.get("/api/report/csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert "migration-report.csv" in resp.headers["content-disposition"]

    # Verify CSV structure
    lines = resp.text.strip().splitlines()
    assert len(lines) >= 2  # header + at least 1 data row
    header = lines[0]
    assert "id" in header
    assert "name" in header
    assert "status" in header
    assert "protocol" in header


async def test_entries_search(client: AsyncClient, mock_app):
    """GET /api/entries?search=sftp filters entries by name."""
    entries = [
        FileEntry(id="s1", name="sftp-config-prod", legacy_config="a", protocol="SFTP"),
        FileEntry(id="s2", name="sftp-config-staging", legacy_config="b", protocol="SFTP"),
        FileEntry(id="s3", name="ftp-config-legacy", legacy_config="c", protocol="FTP"),
    ]
    await mock_app.state_store.load_entries(entries)

    resp = await client.get("/api/entries?search=sftp")
    assert resp.status_code == 200
    data = resp.json()
    # Only the two sftp entries should match
    assert data["total"] == 2
    names = [e["name"] for e in data["entries"]]
    assert "sftp-config-prod" in names
    assert "sftp-config-staging" in names
    assert "ftp-config-legacy" not in names


async def test_rollback_not_found(client: AsyncClient):
    """POST /api/entries/nonexistent/rollback returns 404."""
    resp = await client.post("/api/entries/nonexistent/rollback")
    assert resp.status_code == 404
    assert resp.json()["error"] == "Not found"


async def test_rollback_no_commit(client: AsyncClient, mock_app):
    """POST /api/entries/{id}/rollback returns 400 when entry has no commit_hash."""
    entry = FileEntry(
        id="rb1",
        name="no-commit-entry",
        legacy_config="host=example.com",
        protocol="SFTP",
        status=MigrationStatus.SUCCESS,
        commit_hash="",  # no commit hash
    )
    await mock_app.state_store.load_entries([entry])

    resp = await client.post("/api/entries/rb1/rollback")
    assert resp.status_code == 400
    assert resp.json()["error"] == "No commit to rollback"
