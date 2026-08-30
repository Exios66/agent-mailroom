from __future__ import annotations

import json
import os
from typing import Any

import httpx

from agent_mailroom.config.loader import llm_provider_name
from agent_mailroom.llm import mock


class LLMError(RuntimeError):
    pass


def chat_json(agent: str, system: str, user: str) -> dict[str, Any]:
    provider = llm_provider_name()
    if provider == "mock":
        return _mock_route(agent, user)
    return _http_json(system, user)


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
    if agent == "reporter":
        return {"report": mock.report("document", {})}
    # specialists: first line is DOC_TYPE=
    doc_type = "contract"
    if text.startswith("DOC_TYPE="):
        doc_type = text.split("\n", 1)[0].split("=", 1)[1].strip()
        text = text.split("\n", 1)[1] if "\n" in text else text
    return mock.extract(doc_type, text)


def _http_json(system: str, user: str) -> dict[str, Any]:
    provider = llm_provider_name()
    if provider == "ollama":
        base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
        key = "ollama"
        model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    elif provider == "openai":
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        key = os.environ.get("OPENAI_API_KEY", "")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    else:
        base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        key = os.environ.get("OPENROUTER_API_KEY", "")
        model = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.7-flash")
    if not key and provider != "ollama":
        raise LLMError(f"{provider} selected but no API key is configured")
    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system + "\nReply with a JSON object only."},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    with httpx.Client(timeout=120.0) as client:
        response = client.post(f"{base.rstrip('/')}/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    return json.loads(content)
