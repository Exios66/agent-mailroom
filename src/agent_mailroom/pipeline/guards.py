from __future__ import annotations

import math
from typing import Any

from agent_mailroom.config.loader import extractable_types
from agent_mailroom.schemas.documents import get_extraction_schema, schema_has_substance

GUARD_CLAMP = 0.5


def _coerce_confidence(confidence: Any) -> tuple[float | None, bool]:
    """``(value, ok)``. A string like "high", a bool, NaN or a value outside
    [0, 1] is not a confidence — it used to raise inside ``float()`` and abort
    the whole run as ``unexpected``."""
    if confidence is None or isinstance(confidence, bool):
        return None, False
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return None, False
    if not math.isfinite(value) or value < 0 or value > 1:
        return None, False
    return value, True


def guard_classification(doc_type: str | None, confidence: Any) -> tuple[float, list[str]]:
    flags: list[str] = []
    value, ok = _coerce_confidence(confidence)
    conf = value if ok else GUARD_CLAMP
    if not ok:
        flags.append("bad_confidence")
    if not doc_type or doc_type == "unknown" or doc_type not in extractable_types():
        flags.append("unknown_or_invalid_type")
        conf = min(conf, GUARD_CLAMP)
    return conf, flags


def guard_extraction(doc_type: str | None, extracted: dict[str, Any] | None, confidence: Any) -> tuple[float, list[str]]:
    flags: list[str] = []
    value, ok = _coerce_confidence(confidence)
    conf = value if ok else 0.0
    if not extracted:
        flags.append("empty_extraction")
        return min(conf, GUARD_CLAMP), flags
    schema = get_extraction_schema(doc_type or "")
    if schema is None:
        flags.append("no_schema")
        return min(conf, GUARD_CLAMP), flags
    try:
        model = schema.model_validate({k: v for k, v in extracted.items() if k != "reasoning"})
    except Exception:
        flags.append("schema_invalid")
        return min(conf, GUARD_CLAMP), flags
    if not schema_has_substance(model.model_dump()):
        flags.append("hollow_extraction")
        return min(conf, GUARD_CLAMP), flags
    if not ok:
        flags.append("bad_confidence")
        conf = GUARD_CLAMP
    return conf, flags
