from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from agent_mailroom.config.loader import base_dir, taxonomy


def _path(key: str) -> Path:
    template = taxonomy()["pipeline"]["bins"][key]
    return Path(template.format(base_dir=str(base_dir())))


def inbox_dir() -> Path:
    return _ensure(_path("inbox"))


def processing_dir(doc_id: str) -> Path:
    root = _path("processing")
    return _ensure(_contained(root, root / safe_slug(doc_id, default="doc")))


def review_dir() -> Path:
    return _ensure(_path("review"))


def failed_dir() -> Path:
    return _ensure(_path("failed"))


_SLUG_BAD = re.compile(r"[^A-Za-z0-9._-]+")
_DOC_ID_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def safe_slug(value: str | None, *, default: str = "DEFAULT") -> str:
    """A single safe path segment. ``matter_id`` arrives from upload forms and
    sidecars; "../../x" used to escape the archive root."""
    cleaned = _SLUG_BAD.sub("-", str(value or "")).strip(".-")[:96]
    return cleaned or default


def safe_doc_type(doc_type: str | None) -> str:
    """Only taxonomy doc classes become directories; anything else is ``unknown``."""
    from agent_mailroom.config.loader import live_doc_types

    value = str(doc_type or "")
    return value if value in set(live_doc_types()) else "unknown"


def valid_doc_id(doc_id: str | None) -> bool:
    """Doc ids are interpolated into glob patterns — reject separators / wildcards."""
    return bool(doc_id) and bool(_DOC_ID_OK.match(str(doc_id)))


def _contained(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"path escapes {resolved_root}: {path}")
    return path


def archive_dir(matter_id: str, doc_type: str) -> Path:
    root = _path("archive")
    return _ensure(_contained(root, root / safe_slug(matter_id) / safe_doc_type(doc_type)))


def manifests_dir() -> Path:
    return _ensure(_path("manifests"))


def hive_dir() -> Path:
    return _ensure(_path("hive"))


def classified_dir(doc_type: str | None = None) -> Path:
    root = _ensure(_path("classified"))
    if doc_type:
        return _ensure(root / safe_doc_type(doc_type))
    return root


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_bins() -> None:
    inbox_dir()
    _ensure(_path("processing"))
    classified_dir()
    review_dir()
    failed_dir()
    _ensure(_path("archive"))
    manifests_dir()
    hive_dir()


def atomic_write_text(path: Path, text: str) -> Path:
    """Write via a temp file + ``os.replace`` so readers never see a torn file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def write_manifest(doc_id: str, payload: dict) -> Path:
    path = manifests_dir() / f"{safe_slug(doc_id, default='doc')}.json"
    return atomic_write_text(path, json.dumps(payload, indent=2, default=str))


def load_manifest(doc_id: str) -> dict | None:
    path = manifests_dir() / f"{safe_slug(doc_id, default='doc')}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def safe_filename(name: str | None) -> str:
    base = Path(str(name or "document.txt").replace("\\", "/")).name
    cleaned = base.replace("\x00", "").strip().lstrip(".") or "document.txt"
    return cleaned[:200]


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
    matter_id = safe_slug(matter_id)
    if not valid_doc_id(doc_id):
        raise ValueError(f"invalid doc_id {doc_id!r}")
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
    from agent_mailroom.schemas.manifest import DocumentManifest, PipelineStage
    from agent_mailroom.storage.catalog import upsert_document

    upsert_document(
        DocumentManifest(
            doc_id=doc_id,
            matter_id=matter_id,
            original_filename=name,
            stage=PipelineStage.INBOX,
            graph_node="inbox",
        )
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


def read_inbox_meta(path: Path) -> dict:
    sidecar = path.with_suffix(path.suffix + ".meta")
    if sidecar.exists():
        return json.loads(sidecar.read_text(encoding="utf-8"))
    name = path.name
    doc_id = name.split("--", 1)[0] if "--" in name else ""
    return {"doc_id": doc_id, "filename": name, "matter_id": "DEFAULT", "source": "drop"}


def list_classified_snapshots(limit: int = 80) -> list[dict]:
    """Filesystem snapshots written after classify. Live file may have moved on."""
    ensure_bins()
    root = classified_dir()
    rows: list[dict] = []
    for path in sorted(root.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file() or "--" not in path.name:
            continue
        doc_id, name = path.name.split("--", 1)
        rows.append(
            {
                "doc_id": doc_id,
                "filename": name,
                "doc_type": path.parent.name if path.parent != root else "unknown",
                "bin": "classified",
                "path": str(path),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def copy_classified(src: Path, *, doc_id: str, doc_type: str, filename: str) -> Path:
    dest_dir = classified_dir(doc_type or "unknown")
    dest = dest_dir / f"{doc_id}--{safe_filename(filename)}"
    dest.write_bytes(src.read_bytes())
    return dest


def document_index() -> dict[str, dict]:
    """Every on-disk document in one pass, same precedence as
    ``locate_document`` (live file first, classified snapshot last).

    ``/floor`` used to call ``locate_document`` per row — an inbox scan plus
    two recursive globs each — so 80 runs meant 160 tree walks per poll.
    """
    ensure_bins()
    index: dict[str, dict] = {}

    def put(doc_id: str | None, bin_name: str, path: Path) -> None:
        if doc_id and doc_id not in index:
            index[doc_id] = {"bin": bin_name, "path": path}

    for path in inbox_pending():
        meta = read_inbox_meta(path)
        put(meta.get("doc_id") or (path.name.split("--", 1)[0] if "--" in path.name else None), "inbox", path)
    proc_root = _path("processing")
    if proc_root.exists():
        for folder in sorted(proc_root.iterdir()):
            if folder.is_dir():
                files = sorted(p for p in folder.iterdir() if p.is_file())
                if files:
                    put(folder.name, "processing", files[0])
    for bin_name, root, recursive in (
        ("review", review_dir(), False),
        ("failed", failed_dir(), False),
        ("archive", _path("archive"), True),
        ("classified", _path("classified"), True),
    ):
        if not root.exists():
            continue
        paths = sorted(root.rglob("*--*") if recursive else root.glob("*--*"))
        for path in paths:
            if path.is_file() and not path.name.endswith(".meta"):
                put(path.name.split("--", 1)[0], bin_name, path)
    return index


def locate_document(doc_id: str, index: dict[str, dict] | None = None) -> dict:
    """Find the on-disk tray for a document. Classified is a snapshot; live file wins."""
    if not valid_doc_id(doc_id):
        return {"bin": None, "path": None}
    if index is not None:
        return dict(index.get(doc_id) or {"bin": None, "path": None})
    ensure_bins()
    for path in inbox_pending():
        meta = read_inbox_meta(path)
        if meta.get("doc_id") == doc_id or path.name.startswith(f"{doc_id}--"):
            return {"bin": "inbox", "path": path}
    proc = _path("processing") / doc_id
    if proc.exists():
        files = [p for p in proc.iterdir() if p.is_file()]
        if files:
            return {"bin": "processing", "path": files[0]}
    parked = next(review_dir().glob(f"{doc_id}--*"), None)
    if parked:
        return {"bin": "review", "path": parked}
    failed = next(failed_dir().glob(f"{doc_id}--*"), None)
    if failed:
        return {"bin": "failed", "path": failed}
    archive_root = _path("archive")
    if archive_root.exists():
        hits = sorted(archive_root.rglob(f"{doc_id}--*"))
        files = [p for p in hits if p.is_file()]
        if files:
            return {"bin": "archive", "path": files[0]}
    classified_root = _path("classified")
    if classified_root.exists():
        hits = sorted(classified_root.rglob(f"{doc_id}--*"))
        files = [p for p in hits if p.is_file()]
        if files:
            return {"bin": "classified", "path": files[0]}
    return {"bin": None, "path": None}


def move_file(src: Path, dest_dir: Path, name: str | None = None) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (name or src.name)
    if dest.exists():
        dest = dest_dir / f"{dest.stem}--{src.stat().st_mtime_ns}{dest.suffix}"
    shutil.move(str(src), str(dest))
    return dest


def _same_file_bytes(left: Path, right: Path) -> bool:
    try:
        if left.stat().st_size != right.stat().st_size:
            return False
        return hashlib.sha256(left.read_bytes()).digest() == hashlib.sha256(right.read_bytes()).digest()
    except OSError:
        return False


def requeue_stale_processing(file_path: Path) -> Path:
    """Move a stale processing claim back to the inbox (llm-mailroom v0.6.0).

    Idempotent: if the inbox already has the same bytes, drop the processing
    copy instead of double-queuing. A different file at the same name gets a
    ``--stale`` suffix so the original inbox document is not overwritten.
    """
    inbox = inbox_dir()
    dest = inbox / file_path.name
    if dest.exists():
        if _same_file_bytes(file_path, dest):
            file_path.unlink(missing_ok=True)
            return dest
        stem, suffix = file_path.stem, file_path.suffix
        dest = inbox / f"{stem}--stale{suffix}"
        counter = 2
        while dest.exists():
            dest = inbox / f"{stem}--stale{counter}{suffix}"
            counter += 1
    return move_file(file_path, inbox, dest.name)
