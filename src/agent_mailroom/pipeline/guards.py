from __future__ import annotations

from typing import Any

from agent_mailroom.config.loader import extractable_types
from agent_mailroom.schemas.documents import EXTRACTION_SCHEMAS, schema_has_substance

GUARD_CLAMP = 0.5


def guard_classification(doc_type: str | None, confidence: float | None) -> tuple[float, list[str]]:
    flags: list[str] = []
    conf = 0.0 if confidence is None else float(confidence)
    if confidence is None or conf < 0 or conf > 1:
        flags.append("bad_confidence")
        conf = GUARD_CLAMP
    if not doc_type or doc_type == "unknown" or doc_type not in extractable_types():
        flags.append("unknown_or_invalid_type")
        conf = min(conf, GUARD_CLAMP)
    return conf, flags


def guard_extraction(doc_type: str | None, extracted: dict[str, Any] | None, confidence: float | None) -> tuple[float, list[str]]:
    flags: list[str] = []
    conf = 0.0 if confidence is None else float(confidence)
    if not extracted:
        flags.append("empty_extraction")
        return min(conf, GUARD_CLAMP), flags
    schema = EXTRACTION_SCHEMAS.get(doc_type or "")
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
    if conf < 0 or conf > 1:
        flags.append("bad_confidence")
        conf = GUARD_CLAMP
    return conf, flags
