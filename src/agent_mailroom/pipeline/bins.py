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


def move_file(src: Path, dest_dir: Path, name: str | None = None) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (name or src.name)
    if dest.exists():
        dest = dest_dir / f"{dest.stem}--{src.stat().st_mtime_ns}{dest.suffix}"
    shutil.move(str(src), str(dest))
    return dest
