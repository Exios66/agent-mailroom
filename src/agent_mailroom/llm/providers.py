from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


DEFAULT_MODELS = {
    "openrouter": [
        "qwen/qwen3.7-flash",
        "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v4-pro",
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "anthropic/claude-sonnet-4-20250514",
        "google/gemini-2.0-flash",
    ],
    "openai": ["gpt-4o-mini", "gpt-4o"],
    "ollama": ["qwen2.5:7b", "qwen3:7b", "llama3.1:8b"],
    "vllm": ["*"],
    "generic": ["*"],
    "mock": ["mock"],
}

_MOCK_PLACEHOLDER_KEYS = {
    "",
    "mock-key",
    "changeme",
    "your-key-here",
    "xxx",
    "TODO",
    "replace-me",
}


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str | None
    default_model: str
    available_models: list[str] = field(default_factory=list)
    extra_headers: dict[str, str] = field(default_factory=dict)


def _build_providers() -> dict[str, ProviderConfig]:
    return {
        "openrouter": ProviderConfig(
            name="openrouter",
            base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key_env="OPENROUTER_API_KEY",
            default_model=os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.7-flash"),
            available_models=DEFAULT_MODELS["openrouter"],
            extra_headers={
                "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "https://github.com/Exios66/agent-mailroom"),
                "X-Title": os.environ.get("OPENROUTER_TITLE", "The Mailroom"),
            },
        ),
        "openai": ProviderConfig(
            name="openai",
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key_env="OPENAI_API_KEY",
            default_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            available_models=DEFAULT_MODELS["openai"],
        ),
        "ollama": ProviderConfig(
            name="ollama",
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
            api_key_env=None,
            default_model=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
            available_models=DEFAULT_MODELS["ollama"],
        ),
        "vllm": ProviderConfig(
            name="vllm",
            base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8001/v1"),
            api_key_env="VLLM_API_KEY",
            default_model=os.environ.get("VLLM_MODEL", "*"),
            available_models=DEFAULT_MODELS["vllm"],
        ),
        "generic": ProviderConfig(
            name="generic",
            base_url=os.environ.get("GENERIC_BASE_URL", ""),
            api_key_env="GENERIC_API_KEY",
            default_model=os.environ.get("GENERIC_MODEL", "*"),
            available_models=DEFAULT_MODELS["generic"],
        ),
        "mock": ProviderConfig(
            name="mock",
            base_url="",
            api_key_env=None,
            default_model="mock",
            available_models=DEFAULT_MODELS["mock"],
        ),
    }


def get_providers() -> dict[str, ProviderConfig]:
    return _build_providers()


def requested_provider() -> str:
    return os.environ.get("MAILROOM_LLM_PROVIDER", "openrouter").strip().lower() or "openrouter"


def fallback_provider() -> str:
    return os.environ.get("MAILROOM_LLM_FALLBACK", "mock").strip().lower() or "mock"


def _key_ok(provider: ProviderConfig) -> bool:
    if not provider.api_key_env:
        return True
    key = os.environ.get(provider.api_key_env, "").strip()
    return bool(key) and key not in _MOCK_PLACEHOLDER_KEYS


def _usable(name: str) -> bool:
    providers = get_providers()
    if name not in providers:
        return False
    provider = providers[name]
    if name == "mock":
        return True
    if name == "generic" and not provider.base_url:
        return False
    return _key_ok(provider)


def resolve_harness(agent: str | None = None, agent_cfg: dict[str, Any] | None = None) -> tuple[ProviderConfig, str, dict[str, Any]]:
    """Pick the live harness. OpenRouter is primary; fall back when unconfigured."""
    cfg = dict(agent_cfg or {})
    requested = (cfg.get("provider") or requested_provider()).strip().lower()
    fallback = fallback_provider()
    active = requested if _usable(requested) else fallback
    if not _usable(active):
        active = "mock"
    provider = get_providers()[active]
    model = (
        _agent_model_override(agent)
        or cfg.get("model")
        or provider.default_model
    )
    info = {
        "requested": requested,
        "active": active,
        "fallback": fallback,
        "configured": _usable(requested),
        "model": model,
        "agent": agent,
    }
    return provider, model, info


def _agent_model_override(agent: str | None) -> str | None:
    raw = os.environ.get("MAILROOM_AGENT_MODELS", "")
    if not agent or not raw:
        return None
    for part in raw.split(","):
        if "=" not in part:
            continue
        name, model = part.split("=", 1)
        if name.strip() == agent:
            return model.strip() or None
    return None


def provider_status() -> dict[str, Any]:
    _, model, info = resolve_harness()
    return {
        **info,
        "model": model,
        "harnesses": [
            {
                "name": name,
                "configured": _usable(name),
                "default_model": cfg.default_model,
                "models": cfg.available_models,
            }
            for name, cfg in get_providers().items()
        ],
    }
