from __future__ import annotations

import json
import shutil
from pathlib import Path

from agent_mailroom.config.loader import base_dir, taxonomy


def _path(key: str) -> Path:
    template = taxonomy()["pipeline"]["bins"][key]
    return Path(template.format(base_dir=str(base_dir())))


def inbox_dir() -> Path:
    return _ensure(_path("inbox"))


def processing_dir(doc_id: str) -> Path:
    return _ensure(_path("processing") / doc_id)


def review_dir() -> Path:
    return _ensure(_path("review"))


def failed_dir() -> Path:
    return _ensure(_path("failed"))


def archive_dir(matter_id: str, doc_type: str) -> Path:
    return _ensure(_path("archive") / matter_id / doc_type)


def manifests_dir() -> Path:
    return _ensure(_path("manifests"))


def hive_dir() -> Path:
    return _ensure(_path("hive"))


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_bins() -> None:
    inbox_dir()
    _ensure(_path("processing"))
    review_dir()
    failed_dir()
    _ensure(_path("archive"))
    manifests_dir()
    hive_dir()


def write_manifest(doc_id: str, payload: dict) -> Path:
    path = manifests_dir() / f"{doc_id}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def load_manifest(doc_id: str) -> dict | None:
    path = manifests_dir() / f"{doc_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def safe_filename(name: str | None) -> str:
    base = Path(name or "document.txt").name
    cleaned = base.replace("\x00", "").strip() or "document.txt"
    return cleaned


def enqueue_inbox(
    raw: bytes,
    filename: str,
    *,
    doc_id: str,
    matter_id: str = "DEFAULT",
    source: str = "upload",
) -> Path:
    """Park a file in the inbox with a sidecar. The watcher (or scan_inbox) claims it."""
    name = safe_filename(filename)
    dest = inbox_dir() / f"{doc_id}--{name}"
    dest.write_bytes(raw)
    write_inbox_meta(
        dest,
        {
            "doc_id": doc_id,
            "matter_id": matter_id,
            "source": source,
            "filename": name,
        },
    )
    return dest


def write_inbox_meta(path: Path, payload: dict) -> Path:
    sidecar = path.with_suffix(path.suffix + ".meta")
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return sidecar


def claim_inbox(path: Path, doc_id: str) -> Path:
    dest_dir = processing_dir(doc_id)
    dest = dest_dir / path.name
    if path.resolve() != dest.resolve():
        dest = move_file(path, dest_dir, path.name)
    sidecar = path.with_suffix(path.suffix + ".meta")
    if sidecar.exists():
        sidecar.unlink(missing_ok=True)
    return dest


def inbox_pending() -> list[Path]:
    return [
        path
        for path in inbox_dir().iterdir()
        if path.is_file() and not path.name.endswith(".meta") and not path.name.startswith(".")
    ]


def move_file(src: Path, dest_dir: Path, name: str | None = None) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (name or src.name)
    if dest.exists():
        dest = dest_dir / f"{dest.stem}--{src.stat().st_mtime_ns}{dest.suffix}"
    shutil.move(str(src), str(dest))
    return dest
