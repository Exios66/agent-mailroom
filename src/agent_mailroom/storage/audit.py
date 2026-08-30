from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from agent_mailroom.schemas.audit import AuditLogEntry
from agent_mailroom.storage.catalog import upsert_document
from agent_mailroom.storage.db import connect, init_db, locked
from agent_mailroom.schemas.manifest import DocumentManifest, PipelineStage

HASH_VERSION = 2


def compute_entry_hash(
    *,
    prev_hash: str,
    doc_id: str,
    entry_id: str,
    matter_id: str,
    actor: str,
    timestamp: str,
    event: str,
    detail: dict[str, Any],
) -> str:
    payload = {
        "hash_version": HASH_VERSION,
        "prev_hash": prev_hash,
        "doc_id": doc_id,
        "entry_id": entry_id,
        "matter_id": matter_id,
        "actor": actor,
        "timestamp": timestamp,
        "event": event,
        "detail": detail,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def write_audit(
    *,
    doc_id: str,
    matter_id: str,
    event: str,
    actor: str,
    detail: dict[str, Any] | None = None,
    filename: str | None = None,
) -> AuditLogEntry:
    """Append a hash-chained audit row. Ensures a parent document row exists."""
    init_db()
    detail = dict(detail or {})
    if filename:
        detail.setdefault("original_filename", filename)

    with locked():
        with connect() as conn:
            parent = conn.execute(
                "SELECT doc_id FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
        if parent is None:
            stub = DocumentManifest(
                doc_id=doc_id,
                matter_id=matter_id,
                original_filename=detail.get("original_filename", ""),
                stage=PipelineStage.PROCESSING,
            )
            upsert_document(stub)

        with connect() as conn:
            last = conn.execute(
                "SELECT entry_hash, seq FROM audit_log WHERE doc_id = ? ORDER BY seq DESC LIMIT 1",
                (doc_id,),
            ).fetchone()
            prev_hash = last["entry_hash"] if last else ""
            next_seq = (last["seq"] if last else 0) + 1
            entry = AuditLogEntry(
                doc_id=doc_id,
                matter_id=matter_id,
                event=event,
                actor=actor,
                detail=detail,
                prev_hash=prev_hash,
                seq=next_seq,
            )
            ts = entry.timestamp.astimezone(timezone.utc).isoformat()
            entry.entry_hash = compute_entry_hash(
                prev_hash=prev_hash,
                doc_id=doc_id,
                entry_id=entry.entry_id,
                matter_id=matter_id,
                actor=actor,
                timestamp=ts,
                event=event,
                detail=detail,
            )
            conn.execute(
                """
                INSERT INTO audit_log (
                    entry_id, doc_id, matter_id, event, actor, detail,
                    prev_hash, entry_hash, seq, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_id,
                    entry.doc_id,
                    entry.matter_id,
                    entry.event,
                    entry.actor,
                    json.dumps(entry.detail),
                    entry.prev_hash,
                    entry.entry_hash,
                    entry.seq,
                    ts,
                ),
            )
            conn.commit()
    return entry


def list_audit(doc_id: str) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE doc_id = ? ORDER BY seq, timestamp",
            (doc_id,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["detail"] = json.loads(item["detail"]) if item["detail"] else {}
        out.append(item)
    return out


def verify_chain(doc_id: str) -> tuple[bool, list[dict[str, Any]]]:
    entries = list_audit(doc_id)
    prev = ""
    for entry in entries:
        expected = compute_entry_hash(
            prev_hash=entry["prev_hash"],
            doc_id=entry["doc_id"],
            entry_id=entry["entry_id"],
            matter_id=entry["matter_id"],
            actor=entry["actor"],
            timestamp=entry["timestamp"],
            event=entry["event"],
            detail=entry["detail"],
        )
        if entry["prev_hash"] != prev or entry["entry_hash"] != expected:
            return False, entries
        prev = entry["entry_hash"]
    return True, entries
