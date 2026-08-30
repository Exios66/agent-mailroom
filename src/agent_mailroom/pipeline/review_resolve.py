"""Human-review resolve helpers (llm-mailroom v0.6.0 / The-Mailroom contract).

- ``complete`` archives operator extraction without another LLM pass.
- Empty Complete body falls back to the parked manifest payload.
- Cross-class specialist fields are rejected.
"""

from __future__ import annotations

import json
from typing import Any

from agent_mailroom.schemas.documents import EXTRACTION_SCHEMAS, get_extraction_schema, schema_has_substance

_META_EXTRACT_KEYS = frozenset({"confidence", "reasoning", "mock_extraction"})


def coerce_extracted_data(value: Any) -> dict[str, Any] | None:
    """Normalize operator ``extracted_data``. Empty / missing → ``None``."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            value = json.loads(text)
        except Exception as exc:
            raise ValueError("extracted_data must be a JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError("extracted_data must be a JSON object")
    return value or None


def resolve_complete_extracted(submitted: Any, parked: Any = None) -> dict[str, Any]:
    """Pick operator ``extracted_data``, else the parked manifest payload."""
    chosen = coerce_extracted_data(submitted)
    if chosen:
        return chosen
    chosen = coerce_extracted_data(parked)
    if chosen:
        return chosen
    raise ValueError(
        "disposition=complete requires extracted_data object "
        "(none parked on this document)"
    )


def specialist_schema_keys(doc_type: str) -> frozenset[str]:
    try:
        model = get_extraction_schema(doc_type)
    except KeyError:
        return frozenset()
    return frozenset(model.model_fields)


def all_specialist_schema_keys() -> frozenset[str]:
    names: set[str] = set()
    for model in EXTRACTION_SCHEMAS.values():
        names.update(model.model_fields)
    return frozenset(names) - _META_EXTRACT_KEYS


def validate_operator_extraction(doc_type: str, extracted: dict[str, Any]) -> dict[str, Any]:
    """Reject Complete payloads that do not match the parked document class."""
    if not doc_type:
        raise ValueError("Document has no classification to complete; set override_doc_type")
    payload = dict(extracted)
    allowed = specialist_schema_keys(doc_type) | _META_EXTRACT_KEYS
    foreign = sorted(
        key
        for key in payload
        if key not in allowed
        and not str(key).startswith("_")
        and key in all_specialist_schema_keys()
    )
    if foreign:
        raise ValueError(
            f"extracted_data fields {foreign} belong to another specialist, "
            f"not {doc_type}"
        )
    try:
        model = get_extraction_schema(doc_type)
    except KeyError as exc:
        raise ValueError(f"unknown doc_type for complete: {doc_type}") from exc
    try:
        validated = model.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"extracted_data does not match the {doc_type} schema") from exc
    dumped = validated.model_dump()
    if not schema_has_substance(dumped):
        raise ValueError(f"extracted_data does not match the {doc_type} schema")
    return dumped
