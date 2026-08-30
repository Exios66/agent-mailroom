from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_mailroom.hive.mailbox import deliver
from agent_mailroom.pipeline.bins import locate_document
from agent_mailroom.pipeline.reconsider import enrich_row
from agent_mailroom.pipeline.state import RunState
from agent_mailroom.storage.catalog import list_documents_by_stage, list_review_queue, stuck_documents


def recover_stuck(minutes: int = 15) -> list[dict[str, Any]]:
    """Park stale in-flight claims on review so the floor does not lie."""
    from agent_mailroom.pipeline.runner import park_for_review

    recovered: list[dict[str, Any]] = []
    for row in stuck_documents(minutes):
        loc = locate_document(row["doc_id"])
        path = loc.get("path")
        if not path or loc.get("bin") not in {"processing", "classified", "inbox"}:
            continue
        data = row.get("extracted_data") if isinstance(row.get("extracted_data"), dict) else None
        state = RunState(
            doc_id=row["doc_id"],
            matter_id=row["matter_id"],
            original_filename=row["original_filename"],
            file_path=Path(path),
            doc_type=row.get("doc_type"),
            extracted_data=data,
            routing_path=list(row.get("routing_path") or []),
            escalation_reason="stuck in processing — recovered by ops",
        )
        park_for_review(state)
        recovered.append({"doc_id": row["doc_id"], "from_bin": loc["bin"]})
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
