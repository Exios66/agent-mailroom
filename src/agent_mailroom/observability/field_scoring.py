from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from agent_mailroom.config.loader import taxonomy
from agent_mailroom.storage.db import connect, init_db, locked


def _cfg() -> dict[str, Any]:
    return taxonomy().get("field_scoring") or {}


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_normalize(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    text = str(value).strip().lower()
    return re.sub(r"\s+", " ", text)


def score_field(predicted: Any, expected: Any, *, field_name: str = "") -> dict[str, Any]:
    pred = _normalize(predicted)
    gold = _normalize(expected)
    if not gold and not pred:
        score = 1.0
        method = "both_empty"
    elif not gold:
        score = 0.0
        method = "missing_gt"
    elif not pred:
        score = 0.0
        method = "missing_pred"
    elif pred == gold:
        score = 1.0
        method = "exact"
    else:
        ratio = SequenceMatcher(None, pred, gold).ratio()
        band = _cfg().get("ambiguous_band") or [0.55, 0.85]
        low, high = float(band[0]), float(band[1])
        if ratio >= high:
            score = ratio
            method = "fuzzy_high"
        elif ratio >= low:
            score = ratio
            method = "ambiguous"
        else:
            score = ratio
            method = "fuzzy_low"
    return {
        "field": field_name,
        "score": round(float(score), 4),
        "method": method,
        "predicted": predicted,
        "expected": expected,
    }


def score_extraction(
    predicted: dict[str, Any] | None,
    expected: dict[str, Any] | None,
    *,
    doc_id: str | None = None,
) -> dict[str, Any]:
    predicted = predicted or {}
    expected = expected or {}
    keys = sorted(set(predicted) | set(expected))
    fields = [score_field(predicted.get(k), expected.get(k), field_name=k) for k in keys if not k.startswith("_")]
    scores = [row["score"] for row in fields]
    aggregate = round(sum(scores) / len(scores), 4) if scores else 0.0
    result = {
        "aggregate": aggregate,
        "field_count": len(fields),
        "fields": fields,
    }
    if doc_id:
        persist_scores(doc_id, fields)
    return result


def persist_scores(doc_id: str, fields: list[dict[str, Any]]) -> None:
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with locked():
        with connect() as conn:
            for row in fields:
                conn.execute(
                    """
                    INSERT INTO field_scores (doc_id, field_name, score, method, detail, scored_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(doc_id, field_name) DO UPDATE SET
                      score=excluded.score, method=excluded.method,
                      detail=excluded.detail, scored_at=excluded.scored_at
                    """,
                    (
                        doc_id,
                        row["field"],
                        row["score"],
                        row["method"],
                        json.dumps({"predicted": row.get("predicted"), "expected": row.get("expected")}),
                        now,
                    ),
                )
            conn.commit()


def list_scores(doc_id: str) -> list[dict[str, Any]]:
    with locked():
        with connect() as conn:
            rows = conn.execute(
                "SELECT field_name, score, method, detail, scored_at FROM field_scores WHERE doc_id = ?",
                (doc_id,),
            ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        raw = item.pop("detail", None)
        if raw:
            try:
                item["detail"] = json.loads(raw)
            except json.JSONDecodeError:
                item["detail"] = raw
        out.append(item)
    return out


def metrics_summary() -> dict[str, Any]:
    with locked():
        with connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n, AVG(score) AS avg FROM field_scores"
            ).fetchone()
    return {
        "scored_fields": int(row["n"] or 0),
        "average_score": round(float(row["avg"] or 0.0), 4),
    }
