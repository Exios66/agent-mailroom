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


def field_types(doc_type: str | None) -> dict[str, str]:
    for row in taxonomy().get("doc_classes") or []:
        if row.get("key") == doc_type:
            return dict(row.get("field_types") or {})
    return {}


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


_HARNESS_KEYS = (
    "provider", "model", "temperature", "max_tokens", "max_input_chars",
    "reasoning_effort", "procedural",
)


def agent_config(name: str) -> dict[str, Any]:
    """Per-agent harness from the taxonomy (llm-mailroom agent config shape).

    It used to return only provider/model/role — and the roster carried no
    model — so every agent ran on the global default with a hard-coded
    temperature and no reasoning setting.
    """
    meta = agent_roster().get(name) or {}
    cfg: dict[str, Any] = {key: meta.get(key) for key in _HARNESS_KEYS}
    cfg["role"] = meta.get("role")
    return cfg


def model_map(provider: str) -> dict[str, str]:
    """OpenRouter model id -> local runtime tag for vllm / ollama / llamafile."""
    raw = taxonomy().get(f"{provider}_model_map") or {}
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _num(raw: dict, key: str, default: float) -> float:
    """Configured number, default only when absent/invalid (``x or default``
    turned a deliberate 0 — e.g. ``base_delay: 0`` — into the default)."""
    value = raw.get(key)
    if value is None or isinstance(value, bool):
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def llm_retry() -> dict[str, float]:
    raw = taxonomy().get("llm_retry") or {}
    return {
        "max_attempts": max(1, int(_num(raw, "max_attempts", 5))),
        "base_delay": max(0.0, _num(raw, "base_delay", 1.0)),
        "rate_limit_base_delay": max(0.0, _num(raw, "rate_limit_base_delay", 8.0)),
        "max_delay": max(0.0, _num(raw, "max_delay", 60.0)),
        "jitter": max(0.0, _num(raw, "jitter", 0.3)),
    }


def run_limits() -> dict[str, float]:
    raw = taxonomy().get("run_limits") or {}
    return {
        "llm_call_timeout_seconds": _num(raw, "llm_call_timeout_seconds", 120),
        "deadline_seconds": _num(raw, "deadline_seconds", 3600),
    }


def cost_models() -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for model, prices in (taxonomy().get("cost_models") or {}).items():
        if isinstance(prices, dict):
            try:
                out[str(model)] = (
                    float(prices.get("input_per_million", 0.0)),
                    float(prices.get("output_per_million", 0.0)),
                )
            except (TypeError, ValueError):
                continue
    return out
