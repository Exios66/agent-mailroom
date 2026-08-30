from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent_mailroom.config.loader import accepted_extensions, agent_roster, live_doc_types, stamp_color
from agent_mailroom.hive.mailbox import list_inbox, roster_status
from agent_mailroom.pipeline.bins import inbox_dir, review_dir
from agent_mailroom.pipeline.events import recent
from agent_mailroom.pipeline.runner import fail_document, resume_from_review, run_document
from agent_mailroom.pipeline.state import RunState
from agent_mailroom.storage.audit import list_audit, verify_chain
from agent_mailroom.storage.catalog import get_document, list_documents, list_matters, list_review_queue

router = APIRouter()


def _auth(authorization: str | None) -> None:
    token = os.environ.get("MAILROOM_API_TOKEN", "").strip()
    if not token:
        return
    if not authorization or authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="invalid token")


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "agent-mailroom",
        "producer": True,
        "review_resolve": True,
        "inbox_upload": True,
        "checks": {
            "llm_provider": os.environ.get("MAILROOM_LLM_PROVIDER", "mock"),
            "database": True,
            "watcher": True,
        },
    }


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    matter_id: str = Form("DEFAULT"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _auth(authorization)
    suffix = Path(file.filename or "document.txt").suffix.lower()
    if suffix not in accepted_extensions():
        raise HTTPException(status_code=400, detail=f"unsupported extension {suffix}")
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file too large")
    doc_id = str(uuid4())
    dest = inbox_dir() / f"{doc_id}--{file.filename}"
    dest.write_bytes(raw)
    thread = threading.Thread(
        target=run_document,
        kwargs={"file_path": dest, "matter_id": matter_id, "doc_id": doc_id},
        daemon=True,
        name=f"pipeline-{doc_id[:8]}",
    )
    thread.start()
    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "file": file.filename,
            "upload_id": doc_id,
            "doc_id": doc_id,
            "matter_id": matter_id,
            "message": "queued for the floor",
        },
    )


@router.get("/status/{doc_id}")
def status(doc_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    row = get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="unknown document")
    return row


@router.get("/audit/{doc_id}")
def audit(doc_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    valid, entries = verify_chain(doc_id)
    return {"doc_id": doc_id, "chain_length": len(entries), "chain_valid": valid, "entries": entries}


@router.get("/review/queue")
def review_queue(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    docs = list_review_queue()
    return {
        "review_queue": len(docs),
        "documents": docs,
        "dispositions": ["resume", "record", "requeue", "complete"],
    }


class ResolveBody(BaseModel):
    decision: str
    disposition: str = "resume"
    notes: str | None = None
    doc_type: str | None = None
    override_doc_type: str | None = None
    doc_subclass: str | None = None
    extracted_data: dict[str, Any] | None = None


@router.post("/review/{doc_id}/resolve")
def resolve(
    doc_id: str,
    body: ResolveBody,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _auth(authorization)
    row = get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="unknown document")
    decision = body.decision.lower()
    disposition = body.disposition.lower()
    override = body.override_doc_type or body.doc_type

    if disposition == "record":
        from agent_mailroom.storage.audit import write_audit

        write_audit(doc_id=doc_id, matter_id=row["matter_id"], event="review_recorded", actor="human", detail={"notes": body.notes})
        return {"status": "recorded", "doc_id": doc_id}

    if disposition == "requeue":
        parked = next(review_dir().glob(f"{doc_id}--*"), None)
        if parked is None:
            raise HTTPException(status_code=404, detail="no parked file")
        dest = inbox_dir() / parked.name
        dest.write_bytes(parked.read_bytes())
        thread = threading.Thread(
            target=run_document,
            kwargs={"file_path": dest, "matter_id": row["matter_id"], "doc_id": str(uuid4())},
            daemon=True,
        )
        thread.start()
        from agent_mailroom.storage.audit import write_audit

        write_audit(doc_id=doc_id, matter_id=row["matter_id"], event="review_requeued", actor="human", detail={})
        return {"status": "requeued", "doc_id": doc_id}

    if decision == "rejected" or disposition == "complete" and decision == "rejected":
        parked = next(review_dir().glob(f"{doc_id}--*"), None)
        if parked is None:
            raise HTTPException(status_code=404, detail="no parked file")
        state = RunState(
            doc_id=doc_id,
            matter_id=row["matter_id"],
            original_filename=row["original_filename"],
            file_path=parked,
            routing_path=list(row.get("routing_path") or []),
        )
        fail_document(state, body.notes or "rejected")
        return {"status": "failed", "doc_id": doc_id}

    if disposition == "complete" and decision == "approved":
        from agent_mailroom.pipeline.runner import archive_document

        parked = next(review_dir().glob(f"{doc_id}--*"), None)
        if parked is None:
            raise HTTPException(status_code=404, detail="no parked file")
        state = RunState(
            doc_id=doc_id,
            matter_id=row["matter_id"],
            original_filename=row["original_filename"],
            file_path=parked,
            doc_type=override or row.get("doc_type"),
            extracted_data=body.extracted_data or row.get("extracted_data"),
            routing_path=list(row.get("routing_path") or []),
            report=row.get("report") or "Completed at review desk.",
        )
        archive_document(state)
        return {"status": "archived", "doc_id": doc_id}

    # resume
    if not (override or row.get("doc_type")):
        raise HTTPException(status_code=400, detail="doc_type required to resume")
    thread = threading.Thread(
        target=resume_from_review,
        kwargs={"doc_id": doc_id, "doc_type": override or row.get("doc_type")},
        daemon=True,
    )
    thread.start()
    return {"status": "resumed", "doc_id": doc_id}


@router.get("/queue")
def queue(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    docs = list_documents(200)
    return {
        "queued": [d for d in docs if d["stage"] == "inbox"],
        "processing": [d for d in docs if d["stage"] in {"processing", "classified"}],
        "recent": docs[:20],
    }


@router.get("/lookup")
def lookup(doc_id: str | None = None, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    if not doc_id:
        raise HTTPException(status_code=400, detail="doc_id required")
    row = get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="unknown document")
    return {"document": row}


@router.get("/documents/{doc_id}/source")
def source(doc_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    parked = next(review_dir().glob(f"{doc_id}--*"), None)
    if parked is None:
        raise HTTPException(status_code=404, detail="source not parked")
    return {"doc_id": doc_id, "filename": parked.name, "text": parked.read_text(encoding="utf-8", errors="replace")}


@router.get("/matters/{matter_id}")
def matter(matter_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    docs = list_matters(matter_id)
    return {"matter_id": matter_id, "document_count": len(docs), "documents": docs}


@router.get("/floor")
def floor() -> dict[str, Any]:
    docs = list_documents(80)
    runs = []
    for row in docs:
        stage = row.get("graph_node") or row["stage"]
        display = {
            "human_review": "review",
            "compile_report": "report",
            "catalog_write": "catalog",
            "boss_escalation": "boss",
            "archived": "archived",
            "failed": "failed",
            "review": "review",
        }.get(stage, stage)
        runs.append(
            {
                "trace_id": row["doc_id"],
                "doc_id": row["doc_id"],
                "filename": row["original_filename"],
                "matter_id": row["matter_id"],
                "stage": display if row["stage"] not in {"archived", "failed", "review"} else row["stage"],
                "doc_type": row.get("doc_type"),
                "stamp": stamp_color(row.get("doc_type")),
                "classification_confidence": row.get("classification_confidence"),
                "extraction_confidence": row.get("extraction_confidence"),
                "escalation_reason": row.get("escalation_reason"),
                "needs_human": row["stage"] == "review",
                "routing_path": row.get("routing_path") or [],
                "extracted_data": row.get("extracted_data"),
                "report": row.get("report"),
                "updated_at": row.get("updated_at"),
            }
        )
    return {"count": len(runs), "runs": runs, "roster": agent_roster()}


@router.get("/hive")
def hive() -> dict[str, Any]:
    roster = roster_status()
    inboxes = {name: list_inbox(name, 8) for name in roster}
    return {"registry": roster, "inboxes": inboxes}


@router.get("/console")
def console() -> dict[str, Any]:
    return {"events": recent(120)}


@router.get("/meta")
def meta() -> dict[str, Any]:
    return {
        "service": "agent-mailroom",
        "doc_classes": live_doc_types(),
        "agents": agent_roster(),
        "dispositions": ["resume", "record", "requeue", "complete"],
    }


class DemoBody(BaseModel):
    sample: str = Field(default="all")
    matter_id: str = "DEMO"


@router.post("/demo")
def demo(body: DemoBody | None = None) -> dict[str, Any]:
    """Drop fixture samples onto the floor (mock LLM, no keys)."""
    body = body or DemoBody()
    root = Path(__file__).resolve().parents[3] / "fixtures" / "samples"
    if not root.exists():
        raise HTTPException(status_code=500, detail="fixtures missing")
    files = sorted(root.glob("*.txt"))
    if body.sample != "all":
        files = [p for p in files if body.sample in p.name]
    started = []
    for path in files:
        doc_id = str(uuid4())
        dest = inbox_dir() / f"{doc_id}--{path.name}"
        dest.write_bytes(path.read_bytes())
        threading.Thread(
            target=run_document,
            kwargs={"file_path": dest, "matter_id": body.matter_id, "doc_id": doc_id},
            daemon=True,
        ).start()
        started.append({"doc_id": doc_id, "file": path.name})
    return {"started": started}
