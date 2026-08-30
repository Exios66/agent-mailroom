from __future__ import annotations

from agent_mailroom.pipeline.state import RunState
from agent_mailroom.storage.catalog import list_matters

_GENERIC = {
    "master services agreement",
    "this master services agreement",
    "agreement",
    "the agreement",
}


def _norm(value: str) -> str:
    return " ".join(value.lower().split())


def _is_title(name: str) -> bool:
    n = _norm(name)
    if not n or n in _GENERIC:
        return True
    if "agreement" in n and not any(tok in n for tok in ("inc", "llc", "corporation", "holdings", "company")):
        return True
    return False


def _entities(data: dict | None) -> set[str]:
    if not data:
        return set()
    names: list[str] = []
    if data.get("entity_name"):
        names.append(str(data["entity_name"]))
    for party in data.get("parties") or []:
        names.append(str(party))
    if data.get("insured_party"):
        names.append(str(data["insured_party"]))
    if data.get("insurer"):
        names.append(str(data["insurer"]))
    out = {_norm(name) for name in names if name and not _is_title(str(name))}
    return {item for item in out if item}


def detect_conflict(state: RunState) -> tuple[bool, str | None]:
    mine = _entities(state.extracted_data)
    if not mine:
        return False, None
    for row in list_matters(state.matter_id):
        if row["doc_id"] == state.doc_id:
            continue
        if row.get("doc_type") != state.doc_type:
            continue
        other_data = row.get("extracted_data")
        if not isinstance(other_data, dict):
            continue
        other = _entities(other_data)
        if other and mine.isdisjoint(other):
            left = sorted(mine)[0]
            right = sorted(other)[0]
            return True, f"matter conflict: {left} vs {right}"
    return False, None
