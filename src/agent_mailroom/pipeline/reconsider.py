from __future__ import annotations

from typing import Any


def review_causes(row: dict[str, Any]) -> list[str]:
    """Objective signals that a filing should not look 'done' on the floor."""
    causes: list[str] = []
    stage = row.get("stage") or ""
    reason = (row.get("escalation_reason") or "").lower()
    doc_type = row.get("doc_type") or "unknown"
    data = row.get("extracted_data")
    if isinstance(data, str):
        data = {}
    data = data or {}
    path = [str(step) for step in (row.get("routing_path") or [])]
    extract_conf = row.get("extraction_confidence")
    class_conf = row.get("classification_confidence")

    if stage == "review":
        causes.append("parked")
    if "conflict" in reason or row.get("conflict_detected"):
        causes.append("conflict")
    if doc_type in {"", "unknown", None} or "unknown" in reason:
        causes.append("unknown_class")
    if "failed" in reason or stage == "failed":
        causes.append("node_failure")
    if "judge" in reason or "incomplete" in reason or "partial" in path:
        causes.append("judge_miss")
    if "guard" in reason:
        causes.append("guardrail")
    if stage in {"archived", "review"} and (not data or not any(_filled(v) for v in data.values())):
        if "extract" in path or stage == "archived":
            causes.append("hollow_extraction")
    if extract_conf is not None and extract_conf < 0.70:
        causes.append("low_extraction")
    if class_conf is not None and class_conf < 0.70:
        causes.append("low_classification")
    return list(dict.fromkeys(causes))


def _filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def needs_reconsideration(row: dict[str, Any]) -> bool:
    """Archived/failed filings that still disagree with themselves."""
    if row.get("stage") == "review":
        return False
    causes = set(review_causes(row))
    causes.discard("parked")
    serious = causes & {
        "conflict",
        "hollow_extraction",
        "judge_miss",
        "guardrail",
        "low_extraction",
        "unknown_class",
        "node_failure",
    }
    return bool(serious) and row.get("stage") in {"archived", "failed"}


def enrich_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    causes = review_causes(row)
    out["review_causes"] = causes
    out["needs_reconsideration"] = needs_reconsideration(row)
    out["conflict_detected"] = out.get("conflict_detected") or "conflict" in causes
    return out
