from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_mailroom.hive.mailbox import deliver
from agent_mailroom.pipeline.bins import locate_document, requeue_stale_processing
from agent_mailroom.pipeline.reconsider import enrich_row
from agent_mailroom.schemas.manifest import DocumentManifest, PipelineStage
from agent_mailroom.storage.catalog import list_documents_by_stage, list_review_queue, stuck_documents, upsert_document


def recover_stuck(minutes: int = 15) -> list[dict[str, Any]]:
    """Requeue stale processing claims to the inbox (idempotent --stale).

    Matches llm-mailroom v0.6.0: duplicate inbox bytes are dropped; name
    collisions get a ``--stale`` suffix. Catalog row returns to ``inbox``.
    """
    recovered: list[dict[str, Any]] = []
    for row in stuck_documents(minutes):
        loc = locate_document(row["doc_id"])
        path = loc.get("path")
        if not path or loc.get("bin") not in {"processing", "classified"}:
            continue
        try:
            dest = requeue_stale_processing(Path(path))
        except OSError:
            continue
        upsert_document(
            DocumentManifest(
                doc_id=row["doc_id"],
                matter_id=row["matter_id"],
                original_filename=row["original_filename"],
                stage=PipelineStage.INBOX,
                graph_node="inbox",
                doc_type=row.get("doc_type"),
                extracted_data=row.get("extracted_data") if isinstance(row.get("extracted_data"), dict) else None,
                routing_path=list(row.get("routing_path") or []),
                escalation_reason="stuck in processing — requeued by ops",
            )
        )
        recovered.append({"doc_id": row["doc_id"], "from_bin": loc["bin"], "inbox_path": str(dest)})
    return recovered


def boss_sweep() -> dict[str, Any]:
    """Boss walks the trays and pings the hive for anything still sitting."""
    review = [enrich_row(row) for row in list_review_queue()]
    failed = [enrich_row(row) for row in list_documents_by_stage("failed")]
    stuck = stuck_documents()
    flagged = [enrich_row(row) for row in list_documents_by_stage("archived") if enrich_row(row)["needs_reconsideration"]]
    escalated = 0
    for row in (review + failed + flagged)[:12]:
        deliver(
            sender="boss",
            to="boss",
            act="query",
            subject=f"Sweep: {row.get('original_filename')}",
            body=row.get("escalation_reason") or ",".join(row.get("review_causes") or []),
            doc_id=row.get("doc_id"),
            needs_human=True,
        )
        escalated += 1
    return {
        "review": len(review),
        "failed": len(failed),
        "stuck": len(stuck),
        "reconsider": len(flagged),
        "escalated": escalated,
        "details": [
            {
                "doc_id": row["doc_id"],
                "filename": row.get("original_filename"),
                "stage": row.get("stage"),
                "causes": row.get("review_causes"),
            }
            for row in (review + failed + flagged)[:20]
        ],
    }
