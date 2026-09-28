from __future__ import annotations

import json
import os
import random
import time
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
    return _http_json(provider, model, system, user, info=info, agent_cfg=agent_cfg)


def _mock_route(agent: str, user: str) -> dict[str, Any]:
    text = user
    if agent in {"sorter", "sorter_reviewer"}:
        return mock.classify(text)
    if agent == "judge":
        try:
            payload = text.split("EXTRACTED_JSON\n", 1)[1].split("\n\nSOURCE_TEXT", 1)[0]
            extracted = json.loads(payload)
        except Exception:
            extracted = {"confidence": 0.7}
        return mock.judge(extracted)
    if agent == "arbiter":
        verdict = "partial"
        if "VERDICT=" in text:
            verdict = text.split("VERDICT=", 1)[1].split()[0]
        return mock.arbiter(verdict)
    if agent == "boss":
        return mock.boss("CONFLICT=yes" in text)
    doc_type = "contract"
    if text.startswith("DOC_TYPE="):
        doc_type = text.split("\n", 1)[0].split("=", 1)[1].strip()
        text = text.split("\n", 1)[1] if "\n" in text else text
    return mock.extract(doc_type, text)


def _retry_delay(attempt: int, status: int | None, policy: dict[str, float]) -> float:
    base = policy["rate_limit_base_delay"] if status == 429 else policy["base_delay"]
    delay = min(policy["max_delay"], base * (2 ** attempt))
    jitter = policy.get("jitter") or 0.0
    return max(0.0, delay * (1 + random.uniform(-jitter, jitter)))


def _http_json(
    provider,
    model: str,
    system: str,
    user: str,
    *,
    info: dict[str, Any],
    agent_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from agent_mailroom.config.loader import llm_retry, run_limits

    if not provider.base_url:
        raise LLMError(f"{provider.name} has no base URL")
    if not model:
        raise LLMError(f"{provider.name}: no model configured")
    cfg = agent_cfg or {}
    key = os.environ.get(provider.api_key_env, "").strip() if provider.api_key_env else ""
    max_chars = int(cfg.get("max_input_chars") or 0)
    payload: dict[str, Any] = {
        "model": model,
        "temperature": float(cfg["temperature"]) if cfg.get("temperature") is not None else 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system + "\nReply with a JSON object only. The user message asks for json."},
            {"role": "user", "content": user[:max_chars] if max_chars else user},
        ],
    }
    if cfg.get("max_tokens"):
        payload["max_tokens"] = int(cfg["max_tokens"])
    if cfg.get("reasoning_effort") and provider.name == "openrouter":
        # llm-mailroom sends reasoning.effort via extra_body; "none" matters:
        # reasoning starved JSON output on qwen3.7-flash.
        payload["reasoning"] = {"effort": cfg["reasoning_effort"]}
    headers = dict(provider.extra_headers)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    url = f"{provider.base_url.rstrip('/')}/chat/completions"
    policy = llm_retry()
    timeout = run_limits()["llm_call_timeout_seconds"]
    attempts = max(1, int(policy["max_attempts"]))
    last_error: Exception | None = None
    last_status: int | None = None
    for attempt in range(attempts):
        status: int | None = None
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=payload, headers=headers)
            status = response.status_code
            if status >= 400:
                last_status = status
                last_error = LLMError(f"{provider.name} HTTP {status}: {response.text[:200]}")
                last_error.status_code = status  # type: ignore[attr-defined]
                if status not in _TRANSIENT_STATUS_CODES:
                    break  # 4xx (auth, bad request) never succeeds on retry
            else:
                content = response.json()["choices"][0]["message"]["content"]
                return parse_json_object(content)
        except httpx.TransportError as exc:
            last_error = exc
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            last_error = exc  # malformed body / no JSON object: one more try
        if attempt + 1 < attempts:
            time.sleep(_retry_delay(attempt, status, policy))
    err = LLMError(f"{info.get('active')} harness failed for model {model}: {last_error}")
    if last_status is not None:
        err.status_code = last_status  # type: ignore[attr-defined]
    raise err from last_error
