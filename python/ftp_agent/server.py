"""FastAPI server with REST endpoints and WebSocket log streaming."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
from collections.abc import AsyncGenerator, MutableMapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    FastAPI,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from ftp_agent import __version__
from ftp_agent.app import App, create_app
from ftp_agent.config.settings import AppSettings
from ftp_agent.models.file_entry import MigrationStatus

log = structlog.get_logger()

# Global app instance (set during lifespan)
_app_instance: App | None = None
_run_task: asyncio.Task[None] | None = None
_schedule_task: asyncio.Task[None] | None = None

# WebSocket clients for log streaming
_ws_clients: set[WebSocket] = set()

# Background tasks we need to prevent from being GC'd
_background_tasks: set[asyncio.Task[Any]] = set()


def _get_app() -> App:
    """Return the app instance or raise RuntimeError if not initialized."""
    if _app_instance is None:
        raise RuntimeError("App not initialized — server lifespan has not started.")
    return _app_instance


# --- structlog WebSocket processor ---


def ws_log_processor(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor that broadcasts log events to WebSocket clients."""
    try:
        loop = asyncio.get_running_loop()
        message = {
            k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v))
            for k, v in event_dict.items()
        }
        task = loop.create_task(broadcast_log(message))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        pass  # No running event loop (e.g. CLI mode)
    return event_dict


# --- API Key Auth Middleware ---


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Bearer token auth middleware. Skips /api/health, /ws/, and static files."""

    _SKIP_PREFIXES = ("/api/health", "/ws/")

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        api_key = os.environ.get("FTPAGENT_API_KEY", "")
        if not api_key:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in self._SKIP_PREFIXES):
            return await call_next(request)
        if not path.startswith("/api"):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if auth_header == f"Bearer {api_key}":
            return await call_next(request)

        return JSONResponse({"error": "Unauthorized"}, status_code=401)


# --- Lifespan ---


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncGenerator[None, None]:
    global _app_instance, _schedule_task
    settings = AppSettings()
    _app_instance = create_app(settings, dry_run=True)
    await _app_instance.state_store.initialize()
    log.info("server.started", version=__version__)

    # Start scheduled batch runs if configured
    interval = settings.agent.schedule_interval_hours
    if interval > 0:

        async def _scheduled_run() -> None:
            while True:
                await asyncio.sleep(interval * 3600)
                try:
                    app = _get_app()
                    rpt = await app.orchestrator.run()
                    log.info("server.scheduled_run_complete", success_rate=rpt.success_rate)
                except Exception:
                    log.exception("server.scheduled_run_failed")

        _schedule_task = asyncio.create_task(_scheduled_run())

    yield

    if _schedule_task and not _schedule_task.done():
        _schedule_task.cancel()
    if _app_instance:
        await _app_instance.state_store.close()
        await _app_instance.close()
    log.info("server.stopped")


# --- API Router ---

api_router = APIRouter(prefix="/api")


@api_router.get("/health")
async def health() -> dict[str, Any]:
    app = _get_app()
    llm_healthy = await app.llm.health()
    return {
        "status": "ok",
        "version": __version__,
        "llm_provider": app.llm.provider_name,
        "llm_model": app.llm.model_name,
        "llm_healthy": llm_healthy,
    }


@api_router.get("/status")
async def status() -> dict[str, Any]:
    app = _get_app()
    report = await app.state_store.generate_report()
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
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    app = _get_app()
    if status_filter:
        try:
            ms = MigrationStatus[status_filter.upper()]
            entries = await app.state_store.get_entries_by_status(ms)
        except KeyError:
            return {"error": f"Invalid status: {status_filter}"}
    else:
        entries = await app.state_store.get_all_entries()

    if search:
        term = search.lower()
        entries = [e for e in entries if term in e.name.lower()]

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
async def get_entry(entry_id: str) -> Any:
    app = _get_app()
    entry = await app.state_store.get_entry(entry_id)
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


@api_router.post("/entries/{entry_id}/rollback")
async def rollback_entry(entry_id: str) -> Any:
    app = _get_app()
    entry = await app.state_store.get_entry(entry_id)
    if not entry:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not entry.commit_hash:
        return JSONResponse({"error": "No commit to rollback"}, status_code=400)

    try:
        revert_hash = await app.git_manager.revert_commit(entry.commit_hash)
        await app.state_store.mark_failed(entry_id, f"Rolled back (revert {revert_hash})")
        return {"status": "rolled_back", "revert_commit": revert_hash}
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@api_router.get("/report")
async def report() -> dict[str, Any]:
    app = _get_app()
    rpt = await app.state_store.generate_report()
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


@api_router.get("/report/csv")
async def report_csv() -> StreamingResponse:
    app = _get_app()
    entries = await app.state_store.get_all_entries()

    def generate() -> Any:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["id", "name", "status", "protocol", "retry_count", "last_error",
             "commit_hash", "created_at", "updated_at"]
        )
        for e in entries:
            writer.writerow([
                e.id, e.name, e.status.name, e.protocol, e.retry_count,
                e.last_error, e.commit_hash,
                e.created_at.isoformat(), e.updated_at.isoformat(),
            ])
        buf.seek(0)
        yield buf.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=migration-report.csv"},
    )


@api_router.post("/run")
async def trigger_run(
    background_tasks: BackgroundTasks,
    dry_run: bool = True,
    batch_size: int | None = None,
) -> dict[str, Any]:
    global _run_task
    app = _get_app()

    async def _run() -> None:
        try:
            rpt = await app.orchestrator.run()
            log.info("server.run_complete", success_rate=rpt.success_rate)
        except Exception:
            log.exception("server.run_failed")

    _run_task = asyncio.create_task(_run())
    return {"status": "started", "message": "Migration run triggered in background."}


@api_router.post("/run/stop")
async def stop_run() -> dict[str, Any]:
    app = _get_app()
    app.orchestrator.request_stop()
    return {"status": "stopping", "message": "Graceful stop requested."}


@api_router.get("/config")
async def config_summary() -> dict[str, Any]:
    app = _get_app()
    s = app.settings
    return {
        "agent": {
            "batch_size": s.agent.batch_size,
            "max_retries_per_file": s.agent.max_retries_per_file,
            "poll_interval_seconds": s.agent.poll_interval_seconds,
            "schedule_interval_hours": s.agent.schedule_interval_hours,
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


# --- WebSocket ---


@api_router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket) -> None:
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)


async def broadcast_log(message: dict[str, Any]) -> None:
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


# --- App factory ---


def create_fastapi_app() -> FastAPI:
    cors_origins = os.environ.get("FTPAGENT_CORS_ORIGINS", "*")
    origins = [o.strip() for o in cors_origins.split(",")]

    fastapi_app = FastAPI(
        title="FTP Agent",
        version=__version__,
        lifespan=lifespan,
    )

    fastapi_app.add_middleware(APIKeyMiddleware)
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
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
