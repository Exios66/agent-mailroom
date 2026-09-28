from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from agent_mailroom import __version__
from agent_mailroom.api.routes import active_api_tokens, health, router
from agent_mailroom.api.security import (
    SecurityHeadersMiddleware,
    cors_origins,
    is_public_bind,
    open_mode_allowed,
    origin_allowed,
)
from agent_mailroom.api.ws import bind_loop, hub
from agent_mailroom.config.loader import base_dir
from agent_mailroom.hive.mailbox import seed_hive
from agent_mailroom.office_theme import office_dir
from agent_mailroom.operator.auth import router as auth_router
from agent_mailroom.operator.db import migrate as migrate_operator_db
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
    migrate_operator_db()
    seed_hive()
    start_watcher()
    try:
        yield
    finally:
        stop_watcher()


def create_app() -> FastAPI:
    app = FastAPI(title="The Mailroom", version=__version__, lifespan=lifespan)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    # One mount. The router used to be included twice (bare + /v1), doubling
    # every route and the OpenAPI surface; every client uses /v1. The bare
    # /health stays as an alias for probes written against 0.1.x.
    app.include_router(router, prefix="/v1")
    app.add_api_route("/health", health, methods=["GET"], include_in_schema=False)
    app.include_router(auth_router)

    @app.websocket("/ws")
    async def websocket_floor(ws: WebSocket) -> None:
        # The floor stream carries document names, extractions and reports:
        # same token as the REST API, and browsers must come from an allowed
        # Origin (cross-site WebSocket hijacking).
        if not origin_allowed(ws.headers.get("origin"), ws.headers.get("host")):
            await ws.close(code=1008)
            return
        tokens = active_api_tokens()
        if tokens:
            if (ws.query_params.get("token") or "").strip() not in tokens:
                await ws.close(code=1008)
                return
        elif is_public_bind() and not open_mode_allowed():
            await ws.close(code=1008)
            return
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
