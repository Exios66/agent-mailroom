from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agent_mailroom.schemas.manifest import DocumentManifest, PipelineStage
from agent_mailroom.storage.db import connect, init_db, locked


def upsert_document(manifest: DocumentManifest) -> None:
    init_db()
    manifest.updated_at = datetime.now(timezone.utc)
    payload = (
        manifest.doc_id,
        manifest.matter_id,
        manifest.original_filename,
        manifest.stage.value if isinstance(manifest.stage, PipelineStage) else manifest.stage,
        manifest.graph_node,
        manifest.doc_type,
        manifest.contract_subtype,
        manifest.doc_subclass,
        manifest.classification_confidence,
        manifest.extraction_confidence,
        json.dumps(manifest.extracted_data) if manifest.extracted_data is not None else None,
        manifest.report,
        manifest.escalation_reason,
        manifest.review_decision,
        json.dumps(manifest.routing_path),
        manifest.trace_id,
        manifest.created_at.isoformat(),
        manifest.updated_at.isoformat(),
    )
    sql = """
        INSERT INTO documents (
            doc_id, matter_id, original_filename, stage, graph_node, doc_type,
            contract_subtype, doc_subclass, classification_confidence,
            extraction_confidence, extracted_data, report, escalation_reason,
            review_decision, routing_path, trace_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doc_id) DO UPDATE SET
            matter_id=excluded.matter_id,
            original_filename=excluded.original_filename,
            stage=excluded.stage,
            graph_node=excluded.graph_node,
            doc_type=excluded.doc_type,
            contract_subtype=excluded.contract_subtype,
            doc_subclass=excluded.doc_subclass,
            classification_confidence=excluded.classification_confidence,
            extraction_confidence=excluded.extraction_confidence,
            extracted_data=excluded.extracted_data,
            report=excluded.report,
            escalation_reason=excluded.escalation_reason,
            review_decision=excluded.review_decision,
            routing_path=excluded.routing_path,
            trace_id=excluded.trace_id,
            updated_at=excluded.updated_at
    """
    with locked():
        with connect() as conn:
            conn.execute(sql, payload)
            conn.commit()


def _row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    if data.get("extracted_data"):
        data["extracted_data"] = json.loads(data["extracted_data"])
    if data.get("routing_path"):
        data["routing_path"] = json.loads(data["routing_path"])
    else:
        data["routing_path"] = []
    return data


def get_document(doc_id: str) -> dict[str, Any] | None:
    init_db()
    with locked():
        with connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_documents(limit: int = 200) -> list[dict[str, Any]]:
    init_db()
    with locked():
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_review_queue() -> list[dict[str, Any]]:
    init_db()
    with locked():
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE stage = 'review' ORDER BY updated_at DESC"
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_matters(matter_id: str) -> list[dict[str, Any]]:
    init_db()
    with locked():
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE matter_id = ? ORDER BY created_at",
                (matter_id,),
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_documents_by_stage(stage: str, limit: int = 200) -> list[dict[str, Any]]:
    init_db()
    with locked():
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE stage = ? ORDER BY updated_at DESC LIMIT ?",
                (stage, limit),
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_matters_index() -> list[dict[str, Any]]:
    init_db()
    with locked():
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT matter_id,
                       COUNT(*) AS document_count,
                       SUM(CASE WHEN stage = 'review' THEN 1 ELSE 0 END) AS review_count,
                       SUM(CASE WHEN stage = 'archived' THEN 1 ELSE 0 END) AS archived_count,
                       SUM(CASE WHEN stage = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                       MAX(updated_at) AS updated_at
                FROM documents
                GROUP BY matter_id
                ORDER BY updated_at DESC
                """
            ).fetchall()
    return [dict(row) for row in rows]


def stuck_documents(minutes: int = 15) -> list[dict[str, Any]]:
    init_db()
    with locked():
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM documents
                WHERE stage IN ('processing', 'classified', 'inbox')
                  AND updated_at < datetime('now', ?)
                ORDER BY updated_at
                """,
                (f"-{int(minutes)} minutes",),
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def search_documents(query: str, limit: int = 40) -> list[dict[str, Any]]:
    init_db()
    needle = (query or "").strip()
    if not needle:
        return []
    like = f"%{needle}%"
    with locked():
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM documents
                WHERE doc_id LIKE ? COLLATE NOCASE
                   OR matter_id LIKE ? COLLATE NOCASE
                   OR original_filename LIKE ? COLLATE NOCASE
                   OR COALESCE(doc_type, '') LIKE ? COLLATE NOCASE
                   OR COALESCE(doc_subclass, '') LIKE ? COLLATE NOCASE
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (like, like, like, like, like, limit),
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def touch_matter(matter_id: str, name: str | None = None) -> None:
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with locked():
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO matters (matter_id, name, opened_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(matter_id) DO UPDATE SET updated_at=excluded.updated_at
                """,
                (matter_id, name or matter_id, now, now),
            )
            conn.commit()
