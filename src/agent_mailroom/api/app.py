from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from agent_mailroom.api.routes import router
from agent_mailroom.api.security import SecurityHeadersMiddleware, cors_origins
from agent_mailroom.api.ws import bind_loop, hub
from agent_mailroom.config.loader import base_dir
from agent_mailroom.hive.mailbox import seed_hive
from agent_mailroom.office_theme import office_dir
from agent_mailroom.pipeline.bins import ensure_bins
from agent_mailroom.pipeline.watcher import start_watcher, stop_watcher
from agent_mailroom.storage.db import init_db

OFFICE_DIR = office_dir()


@asynccontextmanager
async def lifespan(app: FastAPI):
    bind_loop(asyncio.get_running_loop())
    base_dir()
    ensure_bins()
    init_db()
    seed_hive()
    start_watcher()
    try:
        yield
    finally:
        stop_watcher()


def create_app() -> FastAPI:
    app = FastAPI(title="The Mailroom", version="0.1.0", lifespan=lifespan)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(router)
    app.include_router(router, prefix="/v1")

    @app.websocket("/ws")
    async def websocket_floor(ws: WebSocket) -> None:
        await hub.connect(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            hub.disconnect(ws)

    if OFFICE_DIR.exists():
        app.mount("/office", StaticFiles(directory=OFFICE_DIR, html=True), name="office")

        @app.get("/")
        def root() -> RedirectResponse:
            return RedirectResponse(url="/office/")

        @app.get("/favicon.ico")
        def favicon() -> FileResponse:
            icon = OFFICE_DIR / "favicon.svg"
            return FileResponse(icon if icon.exists() else OFFICE_DIR / "index.html")
    return app
