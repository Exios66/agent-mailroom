from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_mailroom.config.loader import stamp_color
from agent_mailroom.pipeline.bins import locate_document
from agent_mailroom.pipeline.conflicts import conflict_detail
from agent_mailroom.pipeline.reconsider import enrich_row

DISPLAY_STAGE = {
    "human_review": "review",
    "compile_report": "report",
    "catalog_write": "catalog",
    "boss_escalation": "boss",
    "archived": "archived",
    "failed": "failed",
    "review": "review",
    "inbox": "inbox",
}


def _bin_name(row: dict[str, Any]) -> str | None:
    loc = locate_document(row["doc_id"])
    if loc.get("bin"):
        return loc["bin"]
    stage = row.get("stage")
    if stage in {"inbox", "review", "failed", "archived"}:
        return stage
    if stage in {"processing", "classified"}:
        return stage
    return None


def document_view(row: dict[str, Any]) -> dict[str, Any]:
    enriched = enrich_row(row)
    loc = locate_document(row["doc_id"])
    path = loc.get("path")
    enriched["bin"] = loc.get("bin") or _bin_name(row)
    enriched["bin_path"] = str(path) if path else None
    enriched["stamp"] = stamp_color(row.get("doc_type"))
    enriched["conflict_detail"] = conflict_detail(enriched)
    return enriched


def tray_for_run(run: dict[str, Any]) -> str | None:
    """Parked mail sits on a floor tray. In-flight work stays at a desk."""
    stage = run.get("stage")
    bin_name = run.get("bin")
    if stage == "inbox" or bin_name == "inbox":
        return "inbox"
    if stage == "review" or bin_name == "review":
        return "review"
    if stage in {"archived", "archive"} or bin_name == "archive":
        return "archive"
    if stage == "failed" or bin_name == "failed":
        return "failed"
    if stage == "classified" or bin_name == "classified":
        return "classified"
    return None


def floor_bins(runs: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {
        "inbox": [],
        "classified": [],
        "review": [],
        "archive": [],
        "failed": [],
    }
    for run in runs:
        key = tray_for_run(run)
        if not key:
            continue
        groups[key].append(
            {
                "doc_id": run["doc_id"],
                "filename": run.get("filename") or run.get("original_filename"),
                "stamp": run.get("stamp"),
                "stage": run.get("stage"),
                "matter_id": run.get("matter_id"),
                "doc_type": run.get("doc_type"),
            }
        )
    return {
        key: {"count": len(items), "documents": items[:12]}
        for key, items in groups.items()
    }


def floor_run(row: dict[str, Any]) -> dict[str, Any]:
    view = document_view(row)
    stage = row.get("graph_node") or row["stage"]
    display = DISPLAY_STAGE.get(stage, stage)
    if row["stage"] in {"archived", "failed", "review", "inbox"}:
        display = row["stage"]
    payload = {
        "trace_id": row["doc_id"],
        "doc_id": row["doc_id"],
        "filename": row["original_filename"],
        "matter_id": row["matter_id"],
        "stage": display,
        "doc_type": row.get("doc_type"),
        "doc_subclass": row.get("doc_subclass"),
        "contract_subtype": row.get("contract_subtype"),
        "stamp": view["stamp"],
        "bin": view["bin"],
        "classification_confidence": row.get("classification_confidence"),
        "extraction_confidence": row.get("extraction_confidence"),
        "escalation_reason": row.get("escalation_reason"),
        "needs_human": row["stage"] == "review" or view["needs_reconsideration"],
        "needs_reconsideration": view["needs_reconsideration"],
        "review_causes": view["review_causes"],
        "routing_path": row.get("routing_path") or [],
        "extracted_data": row.get("extracted_data"),
        "report": row.get("report"),
        "updated_at": row.get("updated_at"),
        "conflict_detected": view["conflict_detected"],
        "conflict_detail": view["conflict_detail"],
    }
    payload["tray"] = tray_for_run(payload)
    return payload


def read_source_text(path: Path, limit: int = 200_000) -> str:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if len(text) > limit:
        return text[:limit] + "\n…"
    return text
