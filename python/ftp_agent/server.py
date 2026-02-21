"""FastAPI server with REST endpoints and WebSocket log streaming."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ftp_agent import __version__
from ftp_agent.app import App, create_app
from ftp_agent.config.settings import AppSettings
from ftp_agent.models.file_entry import MigrationStatus

log = structlog.get_logger()

# Global app instance (set during lifespan)
_app_instance: App | None = None
_run_task: asyncio.Task | None = None

# WebSocket clients for log streaming
_ws_clients: set[WebSocket] = set()


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncGenerator[None, None]:
    global _app_instance
    settings = AppSettings()
    _app_instance = create_app(settings, dry_run=True)
    await _app_instance.state_store.initialize()
    log.info("server.started", version=__version__)
    yield
    if _app_instance:
        await _app_instance.state_store.close()
        await _app_instance.close()
    log.info("server.stopped")


# --- API Router ---

api_router = APIRouter(prefix="/api")


@api_router.get("/health")
async def health() -> dict:
    assert _app_instance is not None
    llm_healthy = await _app_instance.llm.health()
    return {
        "status": "ok",
        "version": __version__,
        "llm_provider": _app_instance.llm.provider_name,
        "llm_model": _app_instance.llm.model_name,
        "llm_healthy": llm_healthy,
    }


@api_router.get("/status")
async def status() -> dict:
    assert _app_instance is not None
    report = await _app_instance.state_store.generate_report()
    return {
        "total_files": report.total_files,
        "succeeded": report.succeeded,
        "failed": report.failed,
        "pending": report.pending,
        "in_progress": report.in_progress,
        "retry_pending": report.retry_pending,
        "success_rate": report.success_rate,
    }


@api_router.get("/entries")
async def list_entries(
    status_filter: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    assert _app_instance is not None
    if status_filter:
        try:
            ms = MigrationStatus[status_filter.upper()]
            entries = await _app_instance.state_store.get_entries_by_status(ms)
        except KeyError:
            return {"error": f"Invalid status: {status_filter}"}
    else:
        entries = await _app_instance.state_store.get_all_entries()

    sliced = entries[offset : offset + limit]
    return {
        "total": len(entries),
        "entries": [
            {
                "id": e.id,
                "name": e.name,
                "status": e.status.name,
                "protocol": e.protocol,
                "retry_count": e.retry_count,
                "last_error": e.last_error,
                "commit_hash": e.commit_hash,
                "updated_at": e.updated_at.isoformat(),
            }
            for e in sliced
        ],
    }


@api_router.get("/entries/{entry_id}")
async def get_entry(entry_id: str) -> dict:
    assert _app_instance is not None
    entry = await _app_instance.state_store.get_entry(entry_id)
    if not entry:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {
        "id": entry.id,
        "name": entry.name,
        "status": entry.status.name,
        "protocol": entry.protocol,
        "legacy_config": entry.legacy_config,
        "new_config": entry.new_config,
        "retry_count": entry.retry_count,
        "last_error": entry.last_error,
        "commit_hash": entry.commit_hash,
        "deployment_id": entry.deployment_id,
        "source_path": entry.source_path,
        "destination_path": entry.destination_path,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


@api_router.get("/report")
async def report() -> dict:
    assert _app_instance is not None
    rpt = await _app_instance.state_store.generate_report()
    return {
        "generated_at": rpt.generated_at.isoformat(),
        "total_files": rpt.total_files,
        "succeeded": rpt.succeeded,
        "failed": rpt.failed,
        "pending": rpt.pending,
        "in_progress": rpt.in_progress,
        "retry_pending": rpt.retry_pending,
        "success_rate": rpt.success_rate,
        "summary": rpt.to_summary(),
    }


@api_router.post("/run")
async def trigger_run(
    background_tasks: BackgroundTasks,
    dry_run: bool = True,
    batch_size: int | None = None,
) -> dict:
    global _run_task
    assert _app_instance is not None

    async def _run() -> None:
        try:
            rpt = await _app_instance.orchestrator.run()
            log.info("server.run_complete", success_rate=rpt.success_rate)
        except Exception:
            log.exception("server.run_failed")

    _run_task = asyncio.create_task(_run())
    return {"status": "started", "message": "Migration run triggered in background."}


@api_router.post("/run/stop")
async def stop_run() -> dict:
    assert _app_instance is not None
    _app_instance.orchestrator.request_stop()
    return {"status": "stopping", "message": "Graceful stop requested."}


@api_router.get("/config")
async def config_summary() -> dict:
    assert _app_instance is not None
    s = _app_instance.settings
    return {
        "agent": {
            "batch_size": s.agent.batch_size,
            "max_retries_per_file": s.agent.max_retries_per_file,
            "poll_interval_seconds": s.agent.poll_interval_seconds,
        },
        "llm": {
            "provider": s.llm.provider.value,
        },
        "deployment": {
            "provider": s.deployment.provider.value,
        },
        "monitoring": {
            "provider": s.monitoring.provider.value,
        },
    }


@api_router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket) -> None:
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)


async def broadcast_log(message: dict) -> None:
    """Broadcast a structured log message to all connected WebSocket clients."""
    global _ws_clients
    text = json.dumps(message)
    disconnected: set[WebSocket] = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(text)
        except Exception:
            disconnected.add(ws)
    _ws_clients -= disconnected


def create_fastapi_app() -> FastAPI:
    fastapi_app = FastAPI(
        title="FTP Agent",
        version=__version__,
        lifespan=lifespan,
    )

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    fastapi_app.include_router(api_router)

    # Serve static frontend if built
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        fastapi_app.mount(
            "/",
            StaticFiles(directory=str(static_dir), html=True),
            name="static",
        )

    return fastapi_app
