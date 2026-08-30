from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket

from agent_mailroom.pipeline.events import subscribe


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        payload = json.dumps(event, default=str)
        for ws in list(self.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = Hub()
_loop: asyncio.AbstractEventLoop | None = None


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def _forward(event: dict[str, Any]) -> None:
    loop = _loop
    if loop is None:
        return
    asyncio.run_coroutine_threadsafe(hub.broadcast(event), loop)


subscribe(_forward)
