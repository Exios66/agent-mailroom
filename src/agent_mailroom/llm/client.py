from __future__ import annotations

import json
import os
from typing import Any

import httpx

from agent_mailroom.llm import mock
from agent_mailroom.llm.jsonutil import parse_json_object
from agent_mailroom.llm.providers import resolve_harness


class LLMError(RuntimeError):
    pass


_TRANSIENT_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
_TRANSIENT_MARKERS = ("connection reset", "connection aborted", "temporarily unavailable", "broken pipe")


def is_transient_error(exc: BaseException) -> bool:
    """True when ``exc`` looks like a transient provider/transport failure.

    Covers httpx transport errors (connect/read/write timeouts, connection
    resets, remote protocol errors), retryable HTTP statuses on the exception
    or its attached response, and the provider-marker fallbacks shared with
    the pipeline heuristic in ``pipeline.failures``. Restores the intended
    ``LLM_TRANSIENT`` classification path (hub#46) — the symbol previously
    did not exist, so every classification silently fell through the
    except-and-pass import guard to the heuristic markers.
    """
    if isinstance(exc, httpx.TransportError):
        return True
    status = None
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            status = value
            break
    if status is None:
        response = getattr(exc, "response", None)
        if response is not None:
            value = getattr(response, "status_code", None)
            if isinstance(value, int):
                status = value
    if status in _TRANSIENT_STATUS_CODES:
        return True
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def chat_json(agent: str, system: str, user: str, *, agent_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    provider, model, info = resolve_harness(agent, agent_cfg)
    if provider.name == "mock":
        return _mock_route(agent, user)
    return _http_json(provider, model, system, user, info=info)


def _mock_route(agent: str, user: str) -> dict[str, Any]:
    text = user
    if agent in {"sorter", "sorter_reviewer"}:
        return mock.classify(text)
    if agent == "judge":
        try:
            extracted = json.loads(text.split("EXTRACTED_JSON\n", 1)[1])
        except Exception:
            extracted = {"confidence": 0.7}
        return mock.judge(extracted)
    if agent == "arbiter":
        verdict = "partial"
        if "VERDICT=" in text:
            verdict = text.split("VERDICT=", 1)[1].split()[0]
        return mock.arbiter(verdict)
    if agent == "boss":
        return mock.boss("conflict" in text.lower())
    doc_type = "contract"
    if text.startswith("DOC_TYPE="):
        doc_type = text.split("\n", 1)[0].split("=", 1)[1].strip()
        text = text.split("\n", 1)[1] if "\n" in text else text
    return mock.extract(doc_type, text)


def _http_json(provider, model: str, system: str, user: str, *, info: dict[str, Any]) -> dict[str, Any]:
    if not provider.base_url:
        raise LLMError(f"{provider.name} has no base URL")
    key = os.environ.get(provider.api_key_env, "").strip() if provider.api_key_env else ""
    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system + "\nReply with a JSON object only. The user message asks for json."},
            {"role": "user", "content": user},
        ],
    }
    headers = dict(provider.extra_headers)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    url = f"{provider.base_url.rstrip('/')}/chat/completions"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(url, json=payload, headers=headers)
                if response.status_code in {429, 500, 502, 503} and attempt < 2:
                    last_error = LLMError(f"{provider.name} {response.status_code}")
                    continue
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
            return parse_json_object(content)
        except (httpx.HTTPError, json.JSONDecodeError, ValueError, KeyError) as exc:
            last_error = exc
            if attempt >= 2:
                break
    raise LLMError(f"{info.get('active')} harness failed for model {model}: {last_error}")
