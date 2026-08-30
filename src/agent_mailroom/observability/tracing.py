from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Iterator

from agent_mailroom.observability import spans as local_spans
from agent_mailroom.observability.langfuse_setup import flush_langfuse, observation, pipeline_trace
from agent_mailroom.observability.phoenix_setup import ensure_phoenix, flush_phoenix

_flush_ok = 0
_flush_failures = 0

NODE_OBSERVATION_TYPES = {
    "ingest-document": "span",
    "classify-document": "agent",
    "extract-fields": "agent",
    "judge-verify": "evaluator",
    "arbitrate-verdict": "agent",
    "compile-report": "agent",
    "archive-document": "span",
}


def resolve_provider_name() -> str:
    choice = os.environ.get("OBSERVABILITY_PROVIDER", "auto").strip().lower()
    if choice in {"langfuse", "phoenix", "local", "none"}:
        return choice
    if os.environ.get("LANGFUSE_SECRET_KEY", "").strip():
        return "langfuse"
    if os.environ.get("PHOENIX_TRACING", "").strip().lower() in {"1", "true", "enabled", "yes", "on"}:
        return "phoenix"
    return "local"


def is_enabled() -> bool:
    return resolve_provider_name() != "none"


def _state_summary(state: Any) -> dict[str, Any]:
    if hasattr(state, "snapshot"):
        snap = state.snapshot()
    elif isinstance(state, dict):
        snap = state
    else:
        snap = {}
    return {
        "doc_id": snap.get("doc_id"),
        "matter_id": snap.get("matter_id"),
        "filename": snap.get("original_filename"),
        "doc_type": snap.get("doc_type"),
        "stage": snap.get("stage"),
    }


def _result_summary(state: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if hasattr(state, "snapshot"):
        snap = state.snapshot()
    elif isinstance(state, dict):
        snap = state
    else:
        snap = {}
    out = {
        "stage": snap.get("stage"),
        "doc_type": snap.get("doc_type"),
        "classification_confidence": snap.get("classification_confidence"),
        "extraction_confidence": snap.get("extraction_confidence"),
        "review_decision": snap.get("review_decision"),
    }
    if extra:
        out.update(extra)
    return {k: v for k, v in out.items() if v is not None}


@contextmanager
def span_context(
    doc_id: str,
    name: str,
    *,
    state: Any = None,
    observation_type: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Record a span locally and optionally mirror to Langfuse."""
    obs_type = observation_type or NODE_OBSERVATION_TYPES.get(name, "span")
    inp = _state_summary(state) if state is not None else {"doc_id": doc_id}
    provider = resolve_provider_name()
    holder: dict[str, Any] = {"output": None}
    started = time.perf_counter()
    langfuse_span = None
    if provider == "langfuse":
        with observation(name, as_type=obs_type, input=inp) as lf_span:
            langfuse_span = lf_span
            yield holder
    else:
        yield holder
    latency_ms = (time.perf_counter() - started) * 1000.0
    output = holder.get("output") or (_result_summary(state) if state is not None else None)
    local_spans.record_span(
        doc_id,
        name,
        observation_type=obs_type,
        input_data=inp,
        output_data=output,
        latency_ms=latency_ms,
    )
    if langfuse_span is not None and output is not None:
        try:
            langfuse_span.update(output=output)
        except Exception:
            pass
    if provider == "phoenix":
        ensure_phoenix()
    flush()


def flush() -> None:
    global _flush_ok, _flush_failures
    provider = resolve_provider_name()
    try:
        if provider == "langfuse":
            flush_langfuse()
        elif provider == "phoenix":
            flush_phoenix()
        _flush_ok += 1
    except Exception:
        _flush_failures += 1


def flush_health() -> dict[str, Any]:
    return {
        "provider": resolve_provider_name(),
        "flush_ok": _flush_ok,
        "flush_failures": _flush_failures,
        "healthy": _flush_failures == 0,
    }


__all__ = [
    "flush",
    "flush_health",
    "is_enabled",
    "pipeline_trace",
    "resolve_provider_name",
    "span_context",
]
