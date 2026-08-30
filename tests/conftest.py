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
    from agent_mailroom.config import loader

    loader.taxonomy.cache_clear()
    yield


@pytest.fixture
def samples() -> Path:
    return ROOT / "fixtures" / "samples"
