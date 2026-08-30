from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

log = logging.getLogger(__name__)

_client = None
_init_failed = False


class _NoopSpan:
    def update(self, *args, **kwargs):
        return self

    def end(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        pass


def _keys_present() -> bool:
    return bool(os.environ.get("LANGFUSE_SECRET_KEY", "").strip() and os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip())


def get_client():
    global _client, _init_failed
    if _init_failed or not _keys_present():
        return None
    if _client is not None:
        return _client
    try:
        from langfuse import Langfuse

        host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL") or "http://localhost:3000"
        _client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=host,
        )
        return _client
    except Exception:
        log.warning("langfuse_init_failed", exc_info=True)
        _init_failed = True
        return None


@contextmanager
def pipeline_trace(
    *,
    name: str,
    doc_id: str,
    matter_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any]:
    client = get_client()
    if client is None:
        yield None
        return
    try:
        with client.start_as_current_observation(
            as_type="chain",
            name=name,
            trace_context={"trace_id": doc_id},
            metadata={"matter_id": matter_id, **(metadata or {})},
        ) as root:
            yield root
    except Exception:
        log.warning("langfuse_pipeline_trace_failed", exc_info=True)
        yield None


@contextmanager
def observation(name: str, *, as_type: str = "span", input: dict[str, Any] | None = None) -> Iterator[Any]:
    client = get_client()
    if client is None:
        yield None
        return
    try:
        with client.start_as_current_observation(as_type=as_type, name=name, input=input) as span:
            yield span
    except Exception:
        log.warning("langfuse_observation_failed", name=name, exc_info=True)
        yield None


def flush_langfuse() -> None:
    client = get_client()
    if client is not None:
        client.flush()
