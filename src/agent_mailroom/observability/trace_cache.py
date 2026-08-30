from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = "/tmp/agent-mailroom-trace-cache"
CACHE_SOURCE = "local-cache"


def cache_dir() -> Path:
    raw = (os.environ.get("MAILROOM_TRACE_CACHE_DIR") or DEFAULT_CACHE_DIR).strip()
    return Path(raw or DEFAULT_CACHE_DIR)


def safe_id(trace_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(trace_id))


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".mailroom-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def persist_floor(runs: list[dict[str, Any]], *, source: str = "pipeline") -> None:
    if not runs:
        return
    try:
        _write_json(
            cache_dir() / "traces.json",
            {
                "count": len(runs),
                "source": source,
                "cache_source": CACHE_SOURCE,
                "cached_at": _utcnow(),
                "runs": runs,
            },
        )
    except OSError as exc:
        log.warning("trace cache write failed: %s", exc)


def persist_run(trace_id: str, detail: dict[str, Any]) -> None:
    if not trace_id or not detail:
        return
    body = dict(detail)
    body.setdefault("cached_at", _utcnow())
    try:
        _write_json(cache_dir() / "runs" / f"{safe_id(trace_id)}.json", body)
    except OSError as exc:
        log.warning("run cache write failed: %s", exc)


def load_floor() -> dict[str, Any] | None:
    path = cache_dir() / "traces.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("trace cache unreadable %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def load_run(trace_id: str) -> dict[str, Any] | None:
    path = cache_dir() / "runs" / f"{safe_id(trace_id)}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
