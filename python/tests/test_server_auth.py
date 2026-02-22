"""Tests for API key authentication middleware."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import ftp_agent.server as server_module
from ftp_agent.server import APIKeyMiddleware, api_router


@pytest.fixture
async def mock_app_for_auth(tmp_path):
    """Create a mock app instance for auth tests."""
    from ftp_agent.state.store import StateStore

    store = StateStore(str(tmp_path / "auth_test.db"))
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


def _build_app_with_middleware() -> FastAPI:
    """Build a FastAPI app with the APIKeyMiddleware applied."""
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware)
    app.include_router(api_router)
    return app


@pytest.fixture
async def auth_client(mock_app_for_auth):
    """Create a test client with APIKeyMiddleware applied."""
    app = _build_app_with_middleware()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- Auth middleware tests ---


@patch.dict(os.environ, {"FTPAGENT_API_KEY": ""}, clear=False)
async def test_no_key_configured_allows_all(auth_client: AsyncClient):
    """When FTPAGENT_API_KEY env var is empty, all requests pass through."""
    resp = await auth_client.get("/api/status")
    assert resp.status_code == 200


@patch.dict(os.environ, {"FTPAGENT_API_KEY": "test-secret"}, clear=False)
async def test_health_always_open(auth_client: AsyncClient):
    """GET /api/health succeeds even with auth enabled and no bearer token."""
    resp = await auth_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@patch.dict(os.environ, {"FTPAGENT_API_KEY": "test-secret"}, clear=False)
async def test_missing_bearer_returns_401(auth_client: AsyncClient):
    """When FTPAGENT_API_KEY is set but request has no auth header, returns 401."""
    resp = await auth_client.get("/api/status")
    assert resp.status_code == 401
    assert resp.json()["error"] == "Unauthorized"


@patch.dict(os.environ, {"FTPAGENT_API_KEY": "test-secret"}, clear=False)
async def test_wrong_bearer_returns_401(auth_client: AsyncClient):
    """When bearer token doesn't match, returns 401."""
    resp = await auth_client.get(
        "/api/status",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "Unauthorized"


@patch.dict(os.environ, {"FTPAGENT_API_KEY": "test-secret"}, clear=False)
async def test_correct_bearer_returns_200(auth_client: AsyncClient):
    """When bearer matches FTPAGENT_API_KEY, request succeeds."""
    resp = await auth_client.get(
        "/api/status",
        headers={"Authorization": "Bearer test-secret"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_files" in data


@patch.dict(os.environ, {"FTPAGENT_API_KEY": "test-secret"}, clear=False)
async def test_non_api_paths_skip_auth(mock_app_for_auth):
    """Non-/api paths should not require auth."""
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware)
    app.include_router(api_router)

    # Add a simple non-api route for testing
    @app.get("/hello")
    async def hello():
        return {"message": "world"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # No auth header, but path is not under /api, so it should pass
        resp = await client.get("/hello")
        assert resp.status_code == 200
        assert resp.json()["message"] == "world"
