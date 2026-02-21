"""Tests for FastAPI server endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import ftp_agent.server as server_module
from ftp_agent.server import api_router


@pytest.fixture
async def client(tmp_path):
    """Create a test client with a mock app instance."""
    from ftp_agent.state.store import StateStore

    # Set up a real state store with tmp DB
    store = StateStore(str(tmp_path / "test.db"))
    await store.initialize()

    # Create mock app instance
    mock_app = AsyncMock()
    mock_app.state_store = store
    mock_app.settings = AsyncMock()
    mock_app.settings.agent.batch_size = 10
    mock_app.settings.agent.max_retries_per_file = 3
    mock_app.settings.agent.poll_interval_seconds = 30
    mock_app.settings.llm.provider.value = "minimax"
    mock_app.settings.deployment.provider.value = "stub"
    mock_app.settings.monitoring.provider.value = "stub"
    mock_app.llm.provider_name = "minimax"
    mock_app.llm.model_name = "MiniMax-M2.5"
    mock_app.llm.health = AsyncMock(return_value=True)

    # Inject mock into server module
    original = server_module._app_instance
    server_module._app_instance = mock_app

    # Build a simple FastAPI app with our router (no lifespan needed)
    app = FastAPI()
    app.include_router(api_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    # Cleanup
    server_module._app_instance = original
    await store.close()


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
