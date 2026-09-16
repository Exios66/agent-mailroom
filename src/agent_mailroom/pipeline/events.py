from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Callable

Listener = Callable[[dict[str, Any]], None]

_logger = logging.getLogger("agent_mailroom.pipeline.events")

_lock = threading.Lock()
_listeners: list[Listener] = []
_log: deque[dict[str, Any]] = deque(maxlen=400)


def subscribe(fn: Listener) -> Callable[[], None]:
    with _lock:
        _listeners.append(fn)

    def _unsub() -> None:
        with _lock:
            if fn in _listeners:
                _listeners.remove(fn)

    return _unsub


def emit(event: dict[str, Any]) -> None:
    with _lock:
        _log.append(event)
        listeners = list(_listeners)
    for fn in listeners:
        try:
            fn(event)
        except Exception as exc:
            # Live-or-loud (DMR-061): a dead listener must never swallow the
            # event unseen — name the listener so it can be fixed.
            _logger.warning(
                "event listener %r raised while handling %s event — the "
                "consumer did NOT receive it: %s",
                getattr(fn, "__name__", repr(fn)),
                event.get("type", "?"),
                exc,
            )


def recent(limit: int = 80) -> list[dict[str, Any]]:
    with _lock:
        return list(_log)[-limit:]
