from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agent_mailroom.schemas.manifest import DocumentManifest, PipelineStage
from agent_mailroom.storage.db import connect, init_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    with connect() as conn:
        conn.execute(
            """
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
            """,
            payload,
        )
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
    with connect() as conn:
        row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_documents(limit: int = 200) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM documents ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_review_queue() -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE stage = 'review' ORDER BY updated_at DESC"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_matters(matter_id: str) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE matter_id = ? ORDER BY created_at",
            (matter_id,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]
