from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_started = False


def phoenix_enabled() -> bool:
    raw = os.environ.get("PHOENIX_TRACING", "").strip().lower()
    return raw in {"1", "true", "enabled", "yes", "on"}


def ensure_phoenix() -> bool:
    """Best-effort Phoenix OTEL bootstrap. Returns True when active."""
    global _started
    if _started:
        return True
    if not phoenix_enabled():
        return False
    try:
        from phoenix.otel import register

        endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:6006/v1/traces")
        register(project_name=os.environ.get("PHOENIX_PROJECT", "agent-mailroom"), endpoint=endpoint)
        _started = True
        return True
    except Exception:
        log.warning("phoenix_init_failed", exc_info=True)
        return False


def flush_phoenix() -> None:
    ensure_phoenix()
