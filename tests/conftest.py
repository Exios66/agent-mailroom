from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("MAILROOM_BASE_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAILROOM_LLM_PROVIDER", "mock")
    monkeypatch.setenv("MAILROOM_API_TOKEN", "")
    monkeypatch.setenv("MAILROOM_SYNC", "1")
    # Loopback unless a test opts into a public bind (fail-closed checks).
    monkeypatch.setenv("MAILROOM_HOST", "127.0.0.1")
    monkeypatch.delenv("MAILROOM_ALLOW_OPEN", raising=False)
    monkeypatch.delenv("MAILROOM_TRACE_CACHE_DIR", raising=False)
    from agent_mailroom.config import loader

    loader.taxonomy.cache_clear()
    yield


@pytest.fixture
def samples() -> Path:
    return ROOT / "fixtures" / "samples"
