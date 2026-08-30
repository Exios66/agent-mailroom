"""Field scoring — compatibility shim over ``llm-dojo-scoring`` v0.12.1.

Pinned to the same release as llm-mailroom v0.6.0
(``llm-dojo-scoring @ git+…@v0.12.1``). Core scoring lives in the package;
this module keeps Agent Mailroom glue:

- taxonomy → ``configure()`` wiring
- SQLite persistence (``persist_scores`` / ``list_scores`` / ``metrics_summary``)
- a thin ``score_extraction`` / ``score_field`` façade matching existing callers
"""

from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from typing import Any

from agent_mailroom.config.loader import taxonomy
from agent_mailroom.storage.db import connect, init_db, locked

# json used by persist_scores / list_scores detail payload.

# ---------------------------------------------------------------------------
# Taxonomy → package Settings
# ---------------------------------------------------------------------------


def _apply_taxonomy_settings() -> None:
    """Map ``taxonomy.yaml`` ``field_scoring:`` onto package Settings."""
    try:
        from llm_dojo_scoring import configure
    except ImportError:
        return
    cfg = taxonomy().get("field_scoring") or {}
    if not cfg:
        return
    overrides: dict[str, object] = {}
    band = cfg.get("ambiguous_band")
    if isinstance(band, (list, tuple)) and len(band) == 2:
        overrides["field_scoring__ambiguous_band"] = (float(band[0]), float(band[1]))
    if cfg.get("bipartite_match_threshold") is not None:
        overrides["field_scoring__bipartite_match_threshold"] = float(
            cfg["bipartite_match_threshold"]
        )
    if "embedding_enabled" in cfg:
        overrides["field_scoring__embedding_enabled"] = bool(cfg["embedding_enabled"])
    if cfg.get("embedding_model"):
        overrides["field_scoring__embedding_model"] = str(cfg["embedding_model"])
    if cfg.get("embedding_rescue_below") is not None:
        overrides["field_scoring__embedding_rescue_below"] = float(
            cfg["embedding_rescue_below"]
        )
    pf = cfg.get("partial_gt_fields")
    if isinstance(pf, (list, tuple)) and pf:
        overrides["field_scoring__partial_gt_fields"] = set(pf)
    cf = cfg.get("containment_fields")
    if isinstance(cf, (list, tuple)) and cf:
        overrides["field_scoring__containment_fields"] = set(cf)
    fs = cfg.get("factuality_verification") or {}
    if "enabled" in fs:
        overrides["field_scoring__verification_enabled"] = bool(fs.get("enabled"))
    if fs.get("token_coverage") is not None:
        overrides["field_scoring__verification_token_coverage"] = float(fs["token_coverage"])
    if overrides:
        configure(**overrides)


_apply_taxonomy_settings()

# ---------------------------------------------------------------------------
# Re-exports from llm-dojo-scoring (implementation)
# ---------------------------------------------------------------------------

try:
    from llm_dojo_scoring.field_scoring import (  # noqa: F401
        EntityListScore,
        ExtractionScoreResult,
        FIELD_SCORERS,
        LIST_PREFIX,
        audit_list_field,
        audit_scalar_field,
        disaggregate_clause_spans,
        embedding_enabled,
        get_ambiguous_band,
        get_bipartite_match_threshold,
        get_containment_fields,
        get_embedding_model,
        get_embedding_rescue_below,
        get_field_types as package_get_field_types,
        get_partial_gt_fields,
        get_presence_embedding_threshold,
        get_verification_coverage,
        is_entity_list,
        normalize_text,
        parse_date,
        parse_money,
        score_category_presence,
        score_containment_field,
        score_date_field,
        score_entity_list,
        score_extraction as dojo_score_extraction,
        score_field as dojo_score_field,
        score_free_text_field,
        score_id_field,
        score_money_field,
        score_name_field,
        verify_list_items,
    )
    from llm_dojo_scoring.field_scoring import (  # noqa: F401
        _heuristic_field_type,
    )

    DOJO_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when extra missing
    DOJO_AVAILABLE = False
    dojo_score_extraction = None  # type: ignore[assignment]
    dojo_score_field = None  # type: ignore[assignment]
    package_get_field_types = None  # type: ignore[assignment]
    _heuristic_field_type = None  # type: ignore[assignment]


def get_type_bands() -> dict[str, Any]:
    """Per-field-type ambiguous-band overrides from ``field_scoring.type_bands``."""
    cfg = taxonomy().get("field_scoring") or {}
    bands = cfg.get("type_bands") or {}
    return dict(bands) if isinstance(bands, dict) else {}


def get_field_types(doc_class: str, taxonomy_dict: dict | None = None) -> dict[str, str]:
    """Field→scoring-type map from taxonomy ``doc_classes[].field_types``."""
    if not DOJO_AVAILABLE:
        return {}
    if taxonomy_dict is not None:
        return package_get_field_types(doc_class, taxonomy_dict)
    return package_get_field_types(doc_class, taxonomy())


def _infer_field_types(keys: list[str], predicted: dict, expected: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in keys:
        sample = predicted.get(key, expected.get(key))
        if DOJO_AVAILABLE and _heuristic_field_type is not None:
            out[key] = _heuristic_field_type(key, sample)
        else:
            out[key] = "free_text"
    return out


def score_field(
    predicted: Any,
    expected: Any,
    *,
    field_name: str = "",
    field_type: str | None = None,
) -> dict[str, Any]:
    """Score one field; wraps dojo ``score_field`` and returns a dict for SQLite."""
    if not DOJO_AVAILABLE:
        warnings.warn(
            "llm-dojo-scoring is not installed; install the package pin "
            "(llm-dojo-scoring @ v0.12.1) for production scoring",
            RuntimeWarning,
            stacklevel=2,
        )
        return {
            "field": field_name,
            "score": 0.0,
            "method": "dojo_missing",
            "predicted": predicted,
            "expected": expected,
        }
    ftype = field_type or (
        _heuristic_field_type(field_name, predicted if predicted is not None else expected)
        if field_name
        else "free_text"
    )
    raw = dojo_score_field(ftype, predicted, expected)
    if hasattr(raw, "f1"):
        score = float(raw.f1)
        method = "entity_list"
    elif isinstance(raw, dict):
        score = float(raw.get("score", raw.get("f1", 0.0)))
        method = str(raw.get("method") or "dojo")
    else:
        score = float(raw)
        method = "dojo"
    band = get_ambiguous_band()
    low, high = float(band[0]), float(band[1])
    type_bands = get_type_bands()
    # Normalize entity_list:name → entity_list for band lookup.
    band_key = ftype.split(":", 1)[0] if ":" in ftype else ftype
    override = type_bands.get(band_key)
    if method != "entity_list":
        if override == "always":
            method = "ambiguous"
        elif override == "never":
            method = "exact" if score >= 0.999 else "deterministic"
        elif isinstance(override, (list, tuple)) and len(override) == 2:
            low, high = float(override[0]), float(override[1])
            method = (
                "ambiguous"
                if low <= score < high
                else ("exact" if score >= high else "fuzzy_low")
            )
        else:
            method = (
                "ambiguous"
                if low <= score < high
                else ("exact" if score >= high else "fuzzy_low")
            )
    detail = {
        "predicted": predicted,
        "expected": expected,
        "field_type": ftype,
    }
    if hasattr(raw, "precision"):
        detail.update(
            {
                "precision": raw.precision,
                "recall": raw.recall,
                "matched": raw.matched,
            }
        )
    return {
        "field": field_name,
        "score": round(score, 4),
        "method": method,
        "field_type": ftype,
        "predicted": predicted,
        "expected": expected,
        **{k: v for k, v in detail.items() if k in {"precision", "recall", "matched"}},
    }


def score_extraction(
    predicted: dict[str, Any] | None,
    expected: dict[str, Any] | None,
    *,
    doc_id: str | None = None,
    doc_class: str | None = None,
    field_types: dict[str, str] | None = None,
    doc_text: str | None = None,
) -> dict[str, Any]:
    """Score an extraction against gold using llm-dojo-scoring v0.12.1."""
    predicted = predicted or {}
    expected = expected or {}
    keys = sorted(
        k for k in (set(predicted) | set(expected)) if not str(k).startswith("_")
    )
    resolved_class = doc_class or "contract"
    types = field_types or get_field_types(resolved_class) or _infer_field_types(
        keys, predicted, expected
    )
    for key in keys:
        types.setdefault(key, _heuristic_field_type(key, predicted.get(key, expected.get(key))) if DOJO_AVAILABLE else "free_text")

    if DOJO_AVAILABLE:
        result = dojo_score_extraction(
            resolved_class,
            types,
            predicted,
            expected,
            doc_text=doc_text,
        )
        fields = [
            score_field(
                predicted.get(name),
                expected.get(name),
                field_name=name,
                field_type=types.get(name),
            )
            for name in keys
        ]
        # Prefer dojo overall when present; fall back to mean of field scores.
        aggregate = (
            float(result.overall_score)
            if result.overall_score is not None
            else (round(sum(f["score"] for f in fields) / len(fields), 4) if fields else 0.0)
        )
        payload = {
            "aggregate": round(aggregate, 4),
            "field_count": len(fields),
            "fields": fields,
            "ambiguous_fields": list(result.ambiguous_fields or []),
            "doc_class": result.doc_class,
            "engine": "llm-dojo-scoring==0.12.1",
        }
    else:
        fields = [
            {
                "field": k,
                "score": 0.0,
                "method": "dojo_missing",
                "predicted": predicted.get(k),
                "expected": expected.get(k),
            }
            for k in keys
        ]
        payload = {
            "aggregate": 0.0,
            "field_count": len(fields),
            "fields": fields,
            "engine": "missing",
        }

    if doc_id:
        persist_scores(doc_id, fields)
    return payload


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
                        json.dumps(
                            {
                                "predicted": row.get("predicted"),
                                "expected": row.get("expected"),
                                "field_type": row.get("field_type"),
                            }
                        ),
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
        "engine": "llm-dojo-scoring==0.12.1" if DOJO_AVAILABLE else "missing",
    }
