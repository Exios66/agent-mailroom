from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent_mailroom.api.present import document_view, floor_bins, floor_run, read_source_text
from agent_mailroom.observability.field_scoring import list_scores, metrics_summary
from agent_mailroom.observability.spans import list_spans
from agent_mailroom.observability.trace_cache import load_floor, load_run, persist_floor, persist_run
from agent_mailroom.observability.tracing import flush_health, resolve_provider_name
from agent_mailroom.config.loader import accepted_extensions, agent_roster, live_doc_types, subclass_catalog, taxonomy
from agent_mailroom.llm.providers import provider_status
from agent_mailroom.office_theme import tileset_status
from agent_mailroom.hive.mailbox import list_inbox, roster_status
from agent_mailroom.pipeline.bins import (
    enqueue_inbox,
    inbox_pending,
    list_classified_snapshots,
    locate_document,
    read_inbox_meta,
    review_dir,
    hive_dir,
)
from agent_mailroom.pipeline.events import recent
from agent_mailroom.pipeline.reconsider import enrich_row
from agent_mailroom.pipeline.runner import fail_document, resume_from_review
from agent_mailroom.pipeline.routing import judge_enabled
from agent_mailroom.pipeline.watcher import scan_inbox, status as watcher_status, watcher_lamp
from agent_mailroom.pipeline.topics import (
    complete_topic,
    launch_queued_topic,
    launch_topic,
    office_topics,
    queue_topic,
)
from agent_mailroom.pipeline.state import RunState
from agent_mailroom.storage.audit import verify_chain
from agent_mailroom.storage.catalog import (
    get_document,
    list_documents,
    list_documents_by_stage,
    list_matters,
    list_matters_index,
    list_review_queue,
    search_documents,
)

router = APIRouter()


def _spawn(fn, **kwargs) -> None:
    if os.environ.get("MAILROOM_SYNC") == "1":
        fn(**kwargs)
        return
    threading.Thread(target=fn, kwargs=kwargs, daemon=True, name=f"pipeline-{kwargs.get('doc_id', 'job')}").start()


def _auth(authorization: str | None) -> None:
    token = os.environ.get("MAILROOM_API_TOKEN", "").strip()
    if not token:
        return
    if not authorization or authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="invalid token")


def _accept_inbox(raw: bytes, filename: str, *, doc_id: str, matter_id: str, source: str) -> list[str]:
    """Write inbox + sidecar. Drain immediately under MAILROOM_SYNC; else the watcher claims it."""
    enqueue_inbox(raw, filename, doc_id=doc_id, matter_id=matter_id, source=source)
    if os.environ.get("MAILROOM_SYNC") == "1":
        return scan_inbox()
    return []


def _hive_stats() -> dict[str, Any]:
    roster = roster_status()
    return {
        "agents": len(roster),
        "inbox_total": sum(int(meta.get("inbox_count") or 0) for meta in roster.values()),
    }


@router.get("/health")
def health() -> dict[str, Any]:
    watch = watcher_status()
    lamp = watcher_lamp()
    overall = "ok"
    if lamp in {"stale", "missing"}:
        overall = "degraded"
    return {
        "status": overall,
        "service": "agent-mailroom",
        "producer": True,
        "review_resolve": True,
        "inbox_upload": True,
        "checks": {
            "llm_provider": provider_status()["active"],
            "llm": provider_status(),
            "database": True,
            "watcher": lamp,
            "watcher_embedded": watch["running"],
            "inbox_pending": watch["inbox_pending"],
            "watcher_heartbeat_seconds_ago": watch["heartbeat_age"],
            "tilesets": tileset_status(),
            "desktop": os.environ.get("MAILROOM_DESKTOP") == "1",
            "judge_verify": judge_enabled(),
            "auth_required": bool(os.environ.get("MAILROOM_API_TOKEN", "").strip()),
            "operator_auth": os.environ.get("MAILROOM_OPERATOR_AUTH", "0").strip().lower() in ("1", "true", "on", "yes"),
            "observability": flush_health(),
        },
    }


@router.get("/ops/status")
def ops_status(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    from datetime import datetime, timezone

    from agent_mailroom.storage.db import connect, init_db, locked

    init_db()
    by_stage: dict[str, int] = {}
    by_class: dict[str, int] = {}
    stuck = 0
    with locked():
        with connect() as conn:
            for row in conn.execute("SELECT stage, COUNT(*) AS n FROM documents GROUP BY stage"):
                by_stage[row["stage"]] = row["n"]
            for row in conn.execute(
                "SELECT COALESCE(doc_type, 'unknown') AS c, COUNT(*) AS n FROM documents GROUP BY doc_type"
            ):
                by_class[row["c"]] = row["n"]
            stuck = conn.execute(
                """
                SELECT COUNT(*) AS n FROM documents
                WHERE stage IN ('processing', 'classified', 'inbox')
                  AND updated_at < datetime('now', '-15 minutes')
                """
            ).fetchone()["n"]
    review = list_review_queue()
    reconsider = sum(1 for row in list_documents_by_stage("archived") if enrich_row(row)["needs_reconsideration"])
    return {
        "watcher": watcher_status(),
        "inbox_pending": len(inbox_pending()),
        "documents": by_stage,
        "classes": by_class,
        "review_queue": len(review),
        "stuck_documents": stuck,
        "reconsider": reconsider,
        "bins": {
            "inbox": len(inbox_pending()),
            "classified": len(list_classified_snapshots()),
            "review": len(review),
            "archived": by_stage.get("archived", 0),
            "failed": by_stage.get("failed", 0),
        },
        "hive": _hive_stats(),
        "llm_provider": provider_status()["active"],
        "llm": provider_status(),
        "judge_verify": judge_enabled(),
        "sync": os.environ.get("MAILROOM_SYNC") == "1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
    _accept_inbox(raw, file.filename or "upload.bin", doc_id=doc_id, matter_id=matter_id, source="upload")
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
    return document_view(row)


@router.get("/audit/{doc_id}")
def audit(doc_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    valid, entries = verify_chain(doc_id)
    return {"doc_id": doc_id, "chain_length": len(entries), "chain_valid": valid, "entries": entries}


@router.get("/review/queue")
def review_queue(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    docs = [document_view(row) for row in list_review_queue()]
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
        from agent_mailroom.storage.catalog import upsert_document
        from agent_mailroom.schemas.manifest import DocumentManifest, PipelineStage

        upsert_document(
            DocumentManifest(
                doc_id=doc_id,
                matter_id=row["matter_id"],
                original_filename=row["original_filename"],
                stage=PipelineStage.REVIEW,
                graph_node="human_review",
                doc_type=override or row.get("doc_type"),
                doc_subclass=body.doc_subclass or row.get("doc_subclass"),
                classification_confidence=row.get("classification_confidence"),
                extraction_confidence=row.get("extraction_confidence"),
                extracted_data=body.extracted_data or row.get("extracted_data"),
                report=row.get("report"),
                escalation_reason=row.get("escalation_reason"),
                routing_path=list(row.get("routing_path") or []),
                review_decision="recorded",
            )
        )
        write_audit(
            doc_id=doc_id,
            matter_id=row["matter_id"],
            event="review_recorded",
            actor="human",
            detail={"notes": body.notes, "doc_type": override, "doc_subclass": body.doc_subclass},
        )
        return {"status": "recorded", "doc_id": doc_id}

    if disposition == "requeue":
        parked = next(review_dir().glob(f"{doc_id}--*"), None)
        if parked is None:
            raise HTTPException(status_code=404, detail="no parked file")
        new_id = str(uuid4())
        _accept_inbox(parked.read_bytes(), parked.name, doc_id=new_id, matter_id=row["matter_id"], source="requeue")
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
            doc_subclass=body.doc_subclass or row.get("doc_subclass"),
            extracted_data=body.extracted_data or row.get("extracted_data"),
            routing_path=list(row.get("routing_path") or []),
            report=row.get("report") or "Completed at review desk.",
        )
        archive_document(state)
        return {"status": "archived", "doc_id": doc_id}

    # resume
    if not (override or row.get("doc_type")):
        raise HTTPException(status_code=400, detail="doc_type required to resume")
    _spawn(resume_from_review, doc_id=doc_id, doc_type=override or row.get("doc_type"))
    return {"status": "resumed", "doc_id": doc_id}


@router.get("/queue")
def queue(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    hopper = []
    for path in inbox_pending():
        meta = read_inbox_meta(path)
        hopper.append(
            {
                "doc_id": meta.get("doc_id"),
                "filename": meta.get("filename") or path.name,
                "matter_id": meta.get("matter_id") or "DEFAULT",
                "source": meta.get("source") or "drop",
                "bin": "inbox",
                "path": str(path),
            }
        )
    docs = list_documents(200)
    return {
        "inbox": hopper,
        "queued": hopper,
        "processing": [document_view(d) for d in docs if d["stage"] in {"processing", "classified"}],
        "review": [document_view(d) for d in docs if d["stage"] == "review"],
        "recent": [document_view(d) for d in docs[:20]],
        "counts": {
            "inbox": len(hopper),
            "processing": sum(1 for d in docs if d["stage"] in {"processing", "classified"}),
            "review": sum(1 for d in docs if d["stage"] == "review"),
        },
    }


@router.get("/lookup")
def lookup(doc_id: str | None = None, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    if not doc_id:
        raise HTTPException(status_code=400, detail="doc_id required")
    row = get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="unknown document")
    return {"document": document_view(row)}


@router.get("/search")
def search(q: str = "", authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    needle = (q or "").strip()
    if len(needle) < 2:
        return {"query": needle, "count": 0, "documents": []}
    docs = [document_view(row) for row in search_documents(needle)]
    return {"query": needle, "count": len(docs), "documents": docs}


@router.get("/documents/{doc_id}/source")
def source(doc_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    loc = locate_document(doc_id)
    path = loc.get("path")
    if path is None:
        raise HTTPException(status_code=404, detail="source not on disk")
    return {
        "doc_id": doc_id,
        "filename": path.name,
        "bin": loc.get("bin"),
        "text": read_source_text(path),
    }


@router.get("/inspect/{doc_id}")
def inspect_document(doc_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    row = get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="unknown document")
    view = document_view(row)
    valid, entries = verify_chain(doc_id)
    loc = locate_document(doc_id)
    source_payload = None
    if loc.get("path"):
        source_payload = {
            "filename": loc["path"].name,
            "bin": loc.get("bin"),
            "text": read_source_text(loc["path"]),
        }
    return {
        "document": view,
        "audit": {"chain_valid": valid, "chain_length": len(entries), "entries": entries},
        "source": source_payload,
        "conflict": view.get("conflict_detail"),
        "spans": list_spans(doc_id),
        "field_scores": list_scores(doc_id),
    }


@router.get("/matters")
def matters(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    rows = list_matters_index()
    return {"count": len(rows), "matters": rows}


@router.get("/matters/{matter_id}")
def matter(matter_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    docs = [document_view(row) for row in list_matters(matter_id)]
    return {"matter_id": matter_id, "document_count": len(docs), "documents": docs}


@router.get("/floor")
def floor() -> dict[str, Any]:
    docs = list_documents(80)
    runs = [floor_run(row) for row in docs]
    trays = floor_bins(runs)
    payload = {
        "count": len(runs),
        "runs": runs,
        "roster": agent_roster(),
        "bins": trays,
        "inbox_pending": len(inbox_pending()),
        "review_queue": trays["review"]["count"],
        "reconsider": sum(1 for run in runs if run.get("needs_reconsideration")),
        "failed": trays["failed"]["count"],
        "archived": trays["archive"]["count"],
        "observability_provider": resolve_provider_name(),
    }
    persist_floor(runs)
    return payload


@router.get("/history")
def history(limit: int = 200, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    cached = load_floor()
    docs = list_documents(min(max(limit, 1), 500))
    runs = [floor_run(row) for row in docs]
    if not runs and cached:
        runs = cached.get("runs") or []
    for run in runs[:20]:
        persist_run(run["trace_id"], {"run": run, "spans": list_spans(run["trace_id"])})
    return {
        "count": len(runs),
        "source": "pipeline" if docs else (cached or {}).get("source", "pipeline"),
        "observability_provider": resolve_provider_name(),
        "runs": runs,
    }


@router.get("/runs/{doc_id}")
def run_detail(doc_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    row = get_document(doc_id)
    if not row:
        cached = load_run(doc_id)
        if cached:
            return cached
        raise HTTPException(status_code=404, detail="unknown document")
    run = floor_run(row)
    payload = {
        "trace_id": doc_id,
        "run": run,
        "spans": list_spans(doc_id),
        "field_scores": list_scores(doc_id),
        "routing_path": run.get("routing_path") or [],
        "updated_at": row.get("updated_at"),
        "created_at": row.get("created_at"),
    }
    persist_run(doc_id, payload)
    return payload


@router.get("/metrics")
def metrics(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    docs = list_documents(500)
    runs = [floor_run(row) for row in docs]
    stages: dict[str, int] = {}
    for run in runs:
        stage = str(run.get("stage") or "unknown")
        stages[stage] = stages.get(stage, 0) + 1
    return {
        "documents": len(runs),
        "stages": stages,
        "field_scoring": metrics_summary(),
        "observability": flush_health(),
        "bins": floor_bins(runs),
    }


@router.get("/hive")
def hive() -> dict[str, Any]:
    roster = roster_status()
    inboxes = {name: list_inbox(name, 8) for name in roster}
    board_path = hive_dir() / "board.md"
    board_content = board_path.read_text(encoding="utf-8") if board_path.is_file() else ""
    board_mtime = board_path.stat().st_mtime if board_path.is_file() else None
    return {
        "registry": roster,
        "inboxes": inboxes,
        "board": {"content": board_content, "updated_at": board_mtime},
    }


@router.get("/hive/board")
def hive_board(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    board_path = hive_dir() / "board.md"
    if not board_path.is_file():
        return {"content": "", "updated_at": None}
    return {
        "content": board_path.read_text(encoding="utf-8"),
        "updated_at": board_path.stat().st_mtime,
    }


@router.get("/console")
def console() -> dict[str, Any]:
    return {"events": recent(120)}


@router.get("/meta")
def meta() -> dict[str, Any]:
    tax = taxonomy()
    return {
        "service": "agent-mailroom",
        "doc_classes": live_doc_types(),
        "subclasses": subclass_catalog(),
        "stamps": {row["key"]: row.get("stamp") for row in tax.get("doc_classes", [])},
        "hive_acts": tax.get("hive_acts") or {},
        "trays": ["inbox", "classified", "review", "archive", "failed"],
        "agents": agent_roster(),
        "dispositions": ["resume", "record", "requeue", "complete"],
        "auth_required": bool(os.environ.get("MAILROOM_API_TOKEN", "").strip()),
        "operator_auth": os.environ.get("MAILROOM_OPERATOR_AUTH", "0").strip().lower() in ("1", "true", "on", "yes"),
        "judge_verify": judge_enabled(),
        "observability_provider": resolve_provider_name(),
    }


class TopicBody(BaseModel):
    subject: str
    body: str = ""
    matter_id: str = "DEFAULT"
    route_to: str = "boss"
    ingest: bool | None = None
    action: str = "launch"  # launch | queue


class TopicDispatchBody(BaseModel):
    ingest: bool | None = None


@router.get("/topics")
def topics(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    rows = office_topics()
    queued = [row for row in rows if row["status"] == "queued"]
    live = [row for row in rows if row["status"] in {"assigned", "in_progress"}]
    return {
        "count": len(rows),
        "queued": len(queued),
        "live": len(live),
        "topics": rows,
    }


@router.post("/topics")
def create_topic(body: TopicBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    action = (body.action or "launch").lower()
    if action not in {"launch", "queue"}:
        raise HTTPException(status_code=400, detail="action must be launch or queue")
    try:
        if action == "queue":
            topic = queue_topic(
                subject=body.subject,
                body=body.body,
                matter_id=body.matter_id,
                route_to=body.route_to,
            )
        else:
            topic = launch_topic(
                subject=body.subject,
                body=body.body,
                matter_id=body.matter_id,
                route_to=body.route_to,
                ingest=body.ingest,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": topic["status"], "action": action, "topic": topic}


@router.post("/topics/{topic_id}/launch")
def launch_existing_topic(
    topic_id: str,
    body: TopicDispatchBody | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _auth(authorization)
    body = body or TopicDispatchBody()
    try:
        topic = launch_queued_topic(topic_id, ingest=body.ingest)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown topic") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": topic["status"], "action": "launch", "topic": topic}


@router.post("/topics/{topic_id}/complete")
def finish_topic(topic_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    try:
        topic = complete_topic(topic_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown topic") from exc
    return {"status": "done", "topic": topic}


class DemoBody(BaseModel):
    sample: str = Field(default="all")
    matter_id: str = "DEMO"


class HubPullBody(BaseModel):
    corpus: str = "docclass-pilot"
    limit: int = 5
    offset: int = 0
    config: str | None = None
    split: str | None = None
    matter_id: str = "HUB"


@router.get("/providers")
def providers(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    return provider_status()


@router.get("/datasets")
def datasets(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    from agent_mailroom.pipeline.hf_corpora import CORPORA, ORG, pipeline_corpora

    return {
        "org": ORG,
        "corpora": list(CORPORA.values()),
        "pipeline": pipeline_corpora(),
    }


@router.post("/datasets/pull")
def datasets_pull(body: HubPullBody | None = None, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    from agent_mailroom.pipeline.hub import pull_corpus

    body = body or HubPullBody()
    try:
        return pull_corpus(
            body.corpus,
            limit=body.limit,
            offset=body.offset,
            config=body.config,
            split=body.split,
            matter_id=body.matter_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"hub pull failed: {exc}") from exc


@router.get("/failed")
def failed_list(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    docs = [document_view(row) for row in list_documents_by_stage("failed")]
    return {"count": len(docs), "documents": docs}


@router.get("/classified")
def classified_list(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    snaps = list_classified_snapshots()
    documents = []
    for snap in snaps:
        row = get_document(snap["doc_id"])
        if row:
            view = document_view(row)
            view["classified_path"] = snap["path"]
            view["classified_type"] = snap["doc_type"]
            documents.append(view)
        else:
            documents.append(snap)
    return {"count": len(documents), "documents": documents}


@router.get("/archive")
def archive_list(
    reconsider: bool = False,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _auth(authorization)
    docs = [document_view(row) for row in list_documents_by_stage("archived")]
    if reconsider:
        docs = [doc for doc in docs if doc.get("needs_reconsideration")]
    return {
        "count": len(docs),
        "documents": docs,
        "filter": "reconsider" if reconsider else "all",
    }


@router.get("/reconsider")
def reconsider_list(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    docs = [
        document_view(row)
        for row in list_documents_by_stage("archived")
        if enrich_row(row)["needs_reconsideration"]
    ]
    return {"count": len(docs), "documents": docs}


@router.post("/archive/{doc_id}/requeue")
def archive_requeue(doc_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    from agent_mailroom.storage.audit import write_audit

    row = get_document(doc_id)
    if not row or row.get("stage") != "archived":
        raise HTTPException(status_code=404, detail="not in archive")
    loc = locate_document(doc_id)
    path = loc.get("path")
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="archive file missing")
    new_id = str(uuid4())
    _accept_inbox(
        path.read_bytes(),
        row["original_filename"],
        doc_id=new_id,
        matter_id=row["matter_id"],
        source="reconsider-requeue",
    )
    write_audit(
        doc_id=doc_id,
        matter_id=row["matter_id"],
        event="reconsider_requeued",
        actor="human",
        detail={"new_doc_id": new_id},
        filename=row["original_filename"],
    )
    return {"status": "requeued", "doc_id": new_id, "from_doc_id": doc_id}


@router.get("/archive/{doc_id}")
def archive_one(doc_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    row = get_document(doc_id)
    if not row or row.get("stage") != "archived":
        raise HTTPException(status_code=404, detail="not in archive")
    valid, entries = verify_chain(doc_id)
    view = document_view(row)
    loc = locate_document(doc_id)
    return {
        "document": view,
        "chain_valid": valid,
        "chain_length": len(entries),
        "bin": loc.get("bin"),
        "path": str(loc["path"]) if loc.get("path") else None,
    }


@router.get("/archive/{doc_id}/verify")
def archive_verify(doc_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    valid, entries = verify_chain(doc_id)
    return {"doc_id": doc_id, "chain_valid": valid, "chain_length": len(entries), "entries": entries}


@router.post("/ops/recover")
def ops_recover(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    from agent_mailroom.pipeline.ops import recover_stuck

    recovered = recover_stuck()
    return {"recovered": recovered, "count": len(recovered)}


@router.post("/ops/sweep")
def ops_sweep(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    from agent_mailroom.pipeline.ops import boss_sweep

    return boss_sweep()


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
        _accept_inbox(path.read_bytes(), path.name, doc_id=doc_id, matter_id=body.matter_id, source="demo")
        started.append({"doc_id": doc_id, "file": path.name})
    return {"started": started}
