from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
TAXONOMY_PATH = PACKAGE_DIR / "taxonomy.yaml"


def base_dir() -> Path:
    raw = os.environ.get("MAILROOM_BASE_DIR", "./data")
    path = Path(raw).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def taxonomy() -> dict[str, Any]:
    with TAXONOMY_PATH.open() as fh:
        return yaml.safe_load(fh)


def confidence(doc_type: str | None = None) -> dict[str, float]:
    """Return confidence / Lane B budgets, optionally merged with per-class severity.

    Global keys always present. When ``doc_type`` resolves to a ``by_class``
    entry, that class's ``high`` / ``low`` / ``judge_band_high`` override the
    globals. Retry budgets stay global unless a class entry sets them.
    """
    raw = taxonomy().get("confidence", {}) or {}
    base = {k: v for k, v in raw.items() if k != "by_class"}
    by_class = raw.get("by_class") or {}
    if doc_type and isinstance(by_class, dict):
        overrides = by_class.get(doc_type)
        if isinstance(overrides, dict):
            for key, value in overrides.items():
                if value is not None:
                    base[key] = value
    return base


def live_doc_types() -> list[str]:
    return [row["key"] for row in taxonomy()["doc_classes"]]


def subclass_catalog() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in taxonomy().get("doc_classes", []):
        subs = row.get("subclasses") or []
        if subs:
            out[row["key"]] = [str(s) for s in subs]
    return out


def extractable_types() -> set[str]:
    return set(live_doc_types())


def specialist_for(doc_type: str) -> str:
    for row in taxonomy()["doc_classes"]:
        if row["key"] == doc_type:
            return row["specialist"]
    return "contracts_specialist"


def stamp_color(doc_type: str | None) -> str:
    if not doc_type:
        return "#a09f9f"
    for row in taxonomy()["doc_classes"]:
        if row["key"] == doc_type:
            return row["stamp"]
    return "#a09f9f"


def agent_roster() -> dict[str, dict[str, Any]]:
    return dict(taxonomy()["agents"])


def accepted_extensions() -> set[str]:
    return {ext.lower() for ext in taxonomy()["file_extensions"]}


def llm_provider_name() -> str:
    from agent_mailroom.llm.providers import requested_provider

    return requested_provider()


def agent_config(name: str) -> dict[str, Any]:
    meta = agent_roster().get(name) or {}
    return {
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "role": meta.get("role"),
    }
