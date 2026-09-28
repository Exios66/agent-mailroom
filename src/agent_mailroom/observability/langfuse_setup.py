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
def _guarded(factory, label: str) -> Iterator[Any]:
    """Enter a Langfuse context without ever swallowing the caller's errors.

    The old ``try: with ...: yield`` / ``except: yield None`` shape caught
    exceptions raised *inside* the pipeline body and yielded a second time
    ("generator didn't stop after throw()"), turning every node failure into
    a RuntimeError. Only enter/exit failures are Langfuse's problem.
    """
    try:
        cm = factory()
        handle = cm.__enter__()
    except Exception:
        log.warning("%s_failed", label, exc_info=True)
        yield None
        return
    try:
        yield handle
    except BaseException as exc:
        try:
            suppress = cm.__exit__(type(exc), exc, exc.__traceback__)
        except Exception:
            log.warning("%s_exit_failed", label, exc_info=True)
            suppress = False
        if not suppress:
            raise
    else:
        try:
            cm.__exit__(None, None, None)
        except Exception:
            log.warning("%s_exit_failed", label, exc_info=True)


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
    with _guarded(
        lambda: client.start_as_current_observation(
            as_type="chain",
            name=name,
            trace_context={"trace_id": _trace_id(doc_id)},
            metadata={"matter_id": matter_id, **(metadata or {})},
        ),
        "langfuse_pipeline_trace",
    ) as root:
        yield root


def _trace_id(doc_id: str) -> str:
    """Langfuse v3+ requires 32 lowercase hex chars; uuid4 doc ids qualify
    once the dashes go. Anything else is hashed deterministically."""
    import hashlib

    raw = str(doc_id).replace("-", "").lower()
    if len(raw) == 32 and all(c in "0123456789abcdef" for c in raw):
        return raw
    return hashlib.sha256(str(doc_id).encode("utf-8")).hexdigest()[:32]


@contextmanager
def observation(name: str, *, as_type: str = "span", input: dict[str, Any] | None = None) -> Iterator[Any]:
    client = get_client()
    if client is None:
        yield None
        return
    with _guarded(
        lambda: client.start_as_current_observation(as_type=as_type, name=name, input=input),
        f"langfuse_observation[{name}]",
    ) as span:
        yield span


def flush_langfuse() -> None:
    client = get_client()
    if client is not None:
        client.flush()
