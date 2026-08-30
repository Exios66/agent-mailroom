from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

from agent_mailroom.config.loader import accepted_extensions, base_dir
from agent_mailroom.pipeline.bins import claim_inbox, inbox_dir, inbox_pending
from agent_mailroom.pipeline.events import emit
from agent_mailroom.pipeline.runner import run_document

_stop = threading.Event()
_claimed: set[str] = set()
_lock = threading.Lock()
_thread: threading.Thread | None = None
_heartbeat = 0.0
STALE_AFTER = 5.0


def sync_mode() -> bool:
    return os.environ.get("MAILROOM_SYNC") == "1"


def watcher_enabled() -> bool:
    if sync_mode():
        return False
    return os.environ.get("MAILROOM_WATCHER", "1") != "0"


def heartbeat_age() -> float | None:
    if not _heartbeat:
        return None
    return time.time() - _heartbeat


def is_running() -> bool:
    return bool(_thread and _thread.is_alive())


def watcher_lamp() -> str:
    """llm-mailroom health lamp: ok | stale | missing | off."""
    if sync_mode():
        return "ok"
    if not watcher_enabled():
        return "off"
    if not is_running():
        return "missing"
    age = heartbeat_age()
    if age is None:
        return "missing"
    if age > STALE_AFTER:
        return "stale"
    return "ok"


def status() -> dict:
    return {
        "enabled": watcher_enabled(),
        "running": is_running(),
        "sync": sync_mode(),
        "lamp": watcher_lamp(),
        "heartbeat_age": heartbeat_age(),
        "inbox_pending": len(inbox_pending()),
    }


def _meta_for(path: Path) -> dict:
    sidecar = path.with_suffix(path.suffix + ".meta")
    if sidecar.exists():
        try:
            return json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def claim_and_run(path: Path) -> str | None:
    if not path.is_file():
        return None
    if path.name.endswith(".meta") or path.name.startswith("."):
        return None
    if path.suffix.lower() not in accepted_extensions():
        return None
    key = str(path.resolve())
    with _lock:
        if key in _claimed:
            return None
        _claimed.add(key)
    try:
        if not path.is_file():
            return None
        meta = _meta_for(path)
        doc_id = meta.get("doc_id") or str(uuid4())
        matter_id = meta.get("matter_id") or "DEFAULT"
        claimed = claim_inbox(path, doc_id)
    except Exception:
        with _lock:
            _claimed.discard(key)
        raise
    else:
        with _lock:
            _claimed.discard(key)
    emit({"type": "watcher", "filename": path.name, "doc_id": doc_id, "stage": "inbox"})
    run_document(claimed, matter_id=matter_id, doc_id=doc_id)
    return doc_id


def scan_inbox() -> list[str]:
    started: list[str] = []
    inbox = inbox_dir()
    if not inbox.exists():
        return started
    for path in sorted(inbox.iterdir()):
        try:
            doc_id = claim_and_run(path)
        except Exception:
            emit({"type": "error", "subject": f"watcher failed on {path.name}"})
            continue
        if doc_id:
            started.append(doc_id)
    return started


def _loop() -> None:
    global _heartbeat
    while not _stop.is_set():
        _heartbeat = time.time()
        try:
            (base_dir() / "watcher_heartbeat").write_text(str(_heartbeat), encoding="utf-8")
            scan_inbox()
        except Exception:
            emit({"type": "error", "subject": "watcher loop error"})
        _stop.wait(1.0)


def start_watcher() -> None:
    global _thread
    if not watcher_enabled():
        return
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="inbox-watcher", daemon=True)
    _thread.start()


def stop_watcher() -> None:
    global _thread, _heartbeat
    _stop.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=2.0)
    _thread = None
    _heartbeat = 0.0
