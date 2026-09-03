from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_mailroom.api.app import create_app
from agent_mailroom.observability.field_scoring import score_extraction
from agent_mailroom.observability.spans import list_spans
from agent_mailroom.observability.tracing import resolve_provider_name
from agent_mailroom.operator.auth import create_access_token, decode_token
from agent_mailroom.operator.db import lookup_user, migrate, verify_password


@pytest.fixture
def client():
    return TestClient(create_app())


from agent_mailroom.pipeline.runner import run_document


def test_local_spans_recorded_after_pipeline(samples):
    state = run_document(samples / "harborpoint_msa.txt", matter_id="SPANS", doc_id="span-test-doc")
    spans = list_spans(state.doc_id)
    assert spans
    assert any(span["name"] == "classify-document" for span in spans)


def test_history_and_run_detail(client, samples):
    state = run_document(samples / "harborpoint_msa.txt", matter_id="HIST", doc_id="history-doc")
    history = client.get("/v1/history").json()
    assert history["count"] >= 1
    assert any(row.get("doc_id") == state.doc_id or row.get("trace_id") == state.doc_id for row in history["runs"])
    detail = client.get(f"/v1/runs/{state.doc_id}").json()
    assert detail["trace_id"] == state.doc_id
    assert detail["spans"]


def test_inspect_includes_spans(client, samples):
    state = run_document(samples / "harborpoint_msa.txt", matter_id="INSP", doc_id="inspect-span-doc")
    payload = client.get(f"/v1/inspect/{state.doc_id}").json()
    assert "spans" in payload
    assert payload["spans"]


def test_metrics_endpoint(client):
    payload = client.get("/v1/metrics").json()
    assert "stages" in payload
    assert "observability" in payload
    assert "field_scoring" in payload


def test_field_scoring():
    result = score_extraction(
        {"party_a": "Acme Corp", "effective_date": "2024-01-01"},
        {"party_a": "Acme Corp", "effective_date": "2024-01-02"},
        doc_id="score-doc",
    )
    assert result["aggregate"] > 0
    assert len(result["fields"]) == 2
    assert result["engine"].startswith("llm-dojo-scoring")


def test_dojo_scoring_pin():
    """Agent Mailroom tracks llm-mailroom v0.6.0 → llm-dojo-scoring v0.12.1.

    Release contract = the git pin in pyproject.toml. Monorepo dev resolves
    the pin to the workspace member via [tool.uv.sources], so the installed
    version may be newer than the pin (>= 0.12 required).
    """
    import re
    from pathlib import Path

    import llm_dojo_scoring
    from agent_mailroom.observability import field_scoring as fs

    assert fs.DOJO_AVAILABLE is True
    pin = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "llm-dojo-scoring.git@v0.12.1" in pin
    version = re.match(r"(\d+)\.(\d+)", llm_dojo_scoring.__version__)
    assert version is not None
    assert tuple(map(int, version.groups())) >= (0, 12)
    assert hasattr(fs, "score_extraction")
    assert fs.DOJO_AVAILABLE and hasattr(fs, "ExtractionScoreResult")


def test_observability_provider_default():
    assert resolve_provider_name() in {"local", "langfuse", "phoenix", "none"}


def test_operator_auth_login(client, monkeypatch):
    monkeypatch.setenv("MAILROOM_OPERATOR_AUTH", "1")
    migrate()
    row = lookup_user("operator")
    assert row and verify_password("mailroom", row["password_hash"])
    resp = client.post("/v1/auth/login", json={"username": "operator", "password": "mailroom"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    profile = decode_token(token)
    assert profile.username == "operator"
    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "admin"


def test_vision_helpers_without_pymupdf(tmp_path):
    from agent_mailroom.llm.vision import render_document_pages, vision_enabled

    assert vision_enabled() is True
    txt = tmp_path / "note.txt"
    txt.write_text("plain text", encoding="utf-8")
    assert render_document_pages(txt) == []


def test_tui_once_floor(client, monkeypatch):
    from agent_mailroom.tui import mailroom_console

    monkeypatch.setenv("MAILROOM_API_URL", "http://testserver")
    # TestClient mounts at testserver — use client app via ASGI is harder; just smoke import/main help
    assert mailroom_console.render_floor({"count": 0, "runs": []}).startswith("FLOOR")
