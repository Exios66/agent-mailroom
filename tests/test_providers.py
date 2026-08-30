from agent_mailroom.llm.jsonutil import parse_json_object
from agent_mailroom.llm.providers import resolve_harness


def test_parse_fenced_and_prose_json():
    assert parse_json_object('```json\n{"verdict":"complete"}\n```')["verdict"] == "complete"
    assert parse_json_object('Sure.\n{"decision":"review"}\nThanks')["decision"] == "review"


def test_openrouter_is_primary_and_falls_back_without_key(monkeypatch):
    monkeypatch.setenv("MAILROOM_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("MAILROOM_LLM_FALLBACK", "mock")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    provider, model, info = resolve_harness("sorter")
    assert info["requested"] == "openrouter"
    assert info["active"] == "mock"
    assert info["configured"] is False
    assert provider.name == "mock"
    assert model


def test_openrouter_used_when_key_present(monkeypatch):
    monkeypatch.setenv("MAILROOM_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    provider, model, info = resolve_harness()
    assert info["active"] == "openrouter"
    assert provider.name == "openrouter"
    assert info["configured"] is True
    assert "qwen" in model or "/" in model


def test_agent_model_override(monkeypatch):
    monkeypatch.setenv("MAILROOM_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("MAILROOM_AGENT_MODELS", "judge=deepseek/deepseek-v4-flash")
    _, model, info = resolve_harness("judge")
    assert model == "deepseek/deepseek-v4-flash"
    assert info["agent"] == "judge"
