"""Regression tests for the 0.3.0 audit (sync to llm-mailroom 0.7.1 @959bb0b,
path safety, fail-closed auth, review semantics, tracing, watcher, storage)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent_mailroom.api.app import create_app
from agent_mailroom.pipeline.bins import (
    archive_dir,
    document_index,
    enqueue_inbox,
    locate_document,
    review_dir,
    safe_doc_type,
    safe_slug,
)
from agent_mailroom.pipeline.runner import run_document
from agent_mailroom.storage.catalog import get_document, list_documents


# --------------------------------------------------------------- path safety


def test_archive_dir_cannot_escape_the_archive_root(tmp_path):
    root = archive_dir("DEFAULT", "contract").parents[1].resolve()
    evil = archive_dir("../../../../etc", "../../passwd").resolve()
    assert root in evil.parents
    assert evil.name == "unknown"  # a doc_type outside the taxonomy
    assert safe_slug("../../x") == "x"
    assert safe_slug("") == "DEFAULT"
    assert safe_doc_type("merger_agreement") == "merger_agreement"
    assert safe_doc_type("compliance_filing") == "unknown"  # retired upstream


def test_upload_matter_id_is_slugged(samples):
    client = TestClient(create_app())
    path = samples / "harborpoint_msa.txt"
    resp = client.post(
        "/v1/upload",
        files={"file": (path.name, path.read_bytes(), "text/plain")},
        data={"matter_id": "../../evil"},
    )
    assert resp.status_code == 202
    assert resp.json()["matter_id"] == "evil"
    loc = locate_document(resp.json()["doc_id"])
    assert loc["bin"] == "archive"
    assert "evil" in loc["path"].parts


def test_locate_document_rejects_glob_and_traversal_ids(samples):
    run_document(samples / "acme_claim.txt", matter_id="LOC")
    assert locate_document("*") == {"bin": None, "path": None}
    assert locate_document("../x") == {"bin": None, "path": None}


def test_document_index_matches_locate_document(samples):
    for name in ("acme_claim.txt", "ambiguous_memo.txt", "harborpoint_merger.txt"):
        run_document(samples / name, matter_id="IDX")
    index = document_index()
    for row in list_documents():
        assert locate_document(row["doc_id"], index) == locate_document(row["doc_id"])


# ------------------------------------------------------------- fail closed


def test_public_bind_without_token_fails_closed(monkeypatch):
    monkeypatch.setenv("MAILROOM_HOST", "0.0.0.0")
    client = TestClient(create_app())
    assert client.get("/v1/floor").status_code == 503
    assert client.post("/v1/demo", json={}).status_code == 503
    assert client.get("/v1/health").status_code == 200  # probes stay open
    monkeypatch.setenv("MAILROOM_ALLOW_OPEN", "1")
    assert client.get("/v1/floor").status_code == 200


def test_formerly_open_routes_require_the_token(monkeypatch):
    monkeypatch.setenv("MAILROOM_API_TOKEN", "sekrit")
    client = TestClient(create_app())
    for path in ("/v1/floor", "/v1/hive", "/v1/console"):
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers={"Authorization": "Bearer sekrit"}).status_code == 200, path
    assert client.post("/v1/demo", json={"sample": "nothing-matches"}).status_code == 401


def test_router_is_mounted_once():
    client = TestClient(create_app())
    assert client.get("/floor").status_code == 404
    assert client.get("/health").status_code == 200  # legacy probe alias
    paths = [path for path in client.get("/openapi.json").json()["paths"]]
    assert "/v1/floor" in paths
    assert "/floor" not in paths


def test_websocket_requires_token_and_same_origin(monkeypatch):
    monkeypatch.setenv("MAILROOM_API_TOKEN", "sekrit")
    client = TestClient(create_app())
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()
    with client.websocket_connect("/ws?token=sekrit") as ws:
        ws.send_text("ping")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=sekrit", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_text()


def test_operator_login_refuses_default_secret_on_public_bind(monkeypatch):
    monkeypatch.setenv("MAILROOM_HOST", "0.0.0.0")
    monkeypatch.delenv("MAILROOM_OPERATOR_JWT_SECRET", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    client = TestClient(create_app())
    resp = client.post("/v1/auth/login", json={"username": "operator", "password": "mailroom"})
    assert resp.status_code == 503
    monkeypatch.setenv("MAILROOM_OPERATOR_JWT_SECRET", "a-real-secret")
    resp = client.post("/v1/auth/login", json={"username": "operator", "password": "mailroom"})
    assert resp.status_code == 503  # default admin password still refused
    assert "password" in resp.json()["detail"]


def test_operator_logout_before_any_login_migrates(monkeypatch, tmp_path):
    monkeypatch.setenv("MAILROOM_OPERATOR_DB", str(tmp_path / "fresh-operator.db"))
    from agent_mailroom.operator.db import write_audit

    write_audit(action="logout", metadata={"username": "anonymous"})


# ---------------------------------------------------------- review resolve


def _parked(samples, matter="REV"):
    state = run_document(samples / "ambiguous_memo.txt", matter_id=matter)
    assert get_document(state.doc_id)["stage"] == "review"
    return state.doc_id


def test_reject_parks_in_failed_and_rejected_complete_stays_400(samples):
    client = TestClient(create_app())
    doc_id = _parked(samples)
    bad = client.post(f"/v1/review/{doc_id}/resolve", json={"decision": "rejected", "disposition": "complete"})
    assert bad.status_code == 400  # llm-mailroom contract: complete requires approved
    ok = client.post(f"/v1/review/{doc_id}/resolve", json={"decision": "rejected", "disposition": "resume", "notes": "junk"})
    assert ok.json()["status"] == "failed"
    assert get_document(doc_id)["stage"] == "failed"
    assert locate_document(doc_id)["bin"] == "failed"


def test_resolve_validates_decision_disposition_and_override(samples):
    client = TestClient(create_app())
    doc_id = _parked(samples)
    url = f"/v1/review/{doc_id}/resolve"
    assert client.post(url, json={"decision": "maybe"}).status_code == 400
    assert client.post(url, json={"decision": "approved", "disposition": "yolo"}).status_code == 400
    assert client.post(url, json={"decision": "approved", "doc_type": "compliance_filing"}).status_code == 400
    assert client.post(
        url, json={"decision": "approved", "disposition": "record", "doc_type": "contract", "doc_subclass": "not-a-cuad-family"}
    ).status_code == 400


def test_record_merges_into_the_stored_row(samples):
    client = TestClient(create_app())
    doc_id = _parked(samples)
    before = get_document(doc_id)
    resp = client.post(
        f"/v1/review/{doc_id}/resolve",
        json={"decision": "approved", "disposition": "record", "notes": "looks like a demand", "doc_type": "correspondence"},
    )
    assert resp.status_code == 200
    after = get_document(doc_id)
    assert after["stage"] == "review"
    assert after["routing_path"] == before["routing_path"]
    assert after["classification_confidence"] == before["classification_confidence"]
    assert after["created_at"] == before["created_at"]
    assert "looks like a demand" in after["escalation_reason"]


def test_requeue_closes_the_parked_row(samples):
    client = TestClient(create_app())
    doc_id = _parked(samples)
    resp = client.post(f"/v1/review/{doc_id}/resolve", json={"decision": "approved", "disposition": "requeue"})
    assert resp.status_code == 200
    new_id = resp.json()["new_doc_id"]
    assert not list(review_dir().glob(f"{doc_id}--*"))
    old = get_document(doc_id)
    assert old["stage"] == "failed" and old["review_decision"] == "requeued"
    assert get_document(new_id) is not None


def test_resume_moves_the_parked_copy(samples):
    client = TestClient(create_app())
    doc_id = _parked(samples)
    resp = client.post(
        f"/v1/review/{doc_id}/resolve",
        json={"decision": "approved", "disposition": "resume", "doc_type": "correspondence"},
    )
    assert resp.json()["status"] == "resumed"
    assert not list(review_dir().glob(f"{doc_id}--*"))
    assert get_document(doc_id)["stage"] in {"archived", "review"}


# ----------------------------------------------------------------- runner


def test_safety_cap_parks_instead_of_hanging_in_processing(samples, monkeypatch):
    from agent_mailroom.pipeline import routing

    monkeypatch.setattr(routing, "after_classify", lambda state, retry=False: "classify")
    state = run_document(samples / "harborpoint_msa.txt", matter_id="CAP")
    assert state.stage == "review"
    assert "safety cap" in state.escalation_reason
    assert locate_document(state.doc_id)["bin"] == "review"


def test_merger_fixture_archives_with_effective_time(samples):
    state = run_document(samples / "harborpoint_merger.txt", matter_id="MAUD")
    assert state.stage == "archived"
    assert state.doc_type == "merger_agreement"
    assert state.extracted_data["effective_time"].startswith("12:01 a.m.")
    assert "merger_agreement" in archive_dir("MAUD", "merger_agreement").parts


def test_run_emits_the_document_pipeline_span_names(samples):
    from agent_mailroom.observability.spans import list_spans

    state = run_document(samples / "harborpoint_msa.txt", matter_id="SPANS")
    names = [row["name"] for row in list_spans(state.doc_id)]
    assert names[0] == "intake-document"
    assert "write-catalog" in names and names[-1] == "archive-document"


# ---------------------------------------------------------------- tracing


def test_langfuse_observation_does_not_swallow_body_errors(monkeypatch):
    from agent_mailroom.observability import langfuse_setup

    class FakeClient:
        exited_with = None

        @contextmanager
        def start_as_current_observation(self, **kwargs):
            try:
                yield object()
            except BaseException as exc:
                FakeClient.exited_with = exc
                raise

    monkeypatch.setattr(langfuse_setup, "get_client", lambda: FakeClient())
    with pytest.raises(ValueError, match="node blew up"):
        with langfuse_setup.observation("classify-document", as_type="agent"):
            raise ValueError("node blew up")
    assert isinstance(FakeClient.exited_with, ValueError)


def test_langfuse_enter_failure_degrades_to_none(monkeypatch):
    from agent_mailroom.observability import langfuse_setup

    class Broken:
        def start_as_current_observation(self, **kwargs):
            raise RuntimeError("otel not configured")

    monkeypatch.setattr(langfuse_setup, "get_client", lambda: Broken())
    with langfuse_setup.observation("x") as span:
        assert span is None


def test_span_context_records_failing_nodes():
    from agent_mailroom.observability.spans import list_spans
    from agent_mailroom.observability.tracing import span_context

    enqueue_inbox(b"x", "a.txt", doc_id="span-err", matter_id="S")
    with pytest.raises(KeyError):
        with span_context("span-err", "extract-fields"):
            raise KeyError("boom")
    spans = list_spans("span-err")
    assert spans and spans[-1]["name"] == "extract-fields"
    assert "KeyError" in spans[-1]["output"]["error"]


def test_trace_cache_lives_under_base_dir(tmp_path):
    from agent_mailroom.config.loader import base_dir
    from agent_mailroom.observability.trace_cache import cache_dir

    assert base_dir() in cache_dir().parents


# ------------------------------------------------------- watcher / storage


def test_claim_and_run_releases_the_claim_on_early_return(tmp_path):
    from agent_mailroom.pipeline import watcher

    real = tmp_path / "vanishing.txt"
    real.write_text("hello", encoding="utf-8")

    class Vanishing(type(real)):
        _calls = 0

        def is_file(self):  # present for the guard, gone after the claim
            Vanishing._calls += 1
            return Vanishing._calls == 1

    path = Vanishing(real)
    assert watcher.claim_and_run(path) is None
    assert watcher._claimed == set()


def test_stuck_documents_compare_iso_timestamps(samples):
    from datetime import datetime, timedelta, timezone

    from agent_mailroom.storage.catalog import stuck_documents
    from agent_mailroom.storage.db import connect, locked

    state = run_document(samples / "acme_claim.txt", matter_id="STUCK")
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    with locked():
        with connect() as conn:
            conn.execute("UPDATE documents SET stage='processing', updated_at=? WHERE doc_id=?", (fresh, state.doc_id))
            conn.commit()
    assert all(row["doc_id"] != state.doc_id for row in stuck_documents(15))
    assert any(row["doc_id"] == state.doc_id for row in stuck_documents(1))


def test_connections_close_after_with_block():
    from agent_mailroom.storage.db import connect, init_db

    init_db()
    with connect() as conn:
        conn.execute("SELECT 1").fetchone()
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_health_reports_a_real_database_probe():
    client = TestClient(create_app())
    body = client.get("/v1/health").json()
    assert body["checks"]["database"] is True


def test_source_endpoint_reads_once_and_flags_truncation(samples):
    client = TestClient(create_app())
    state = run_document(samples / "harborpoint_msa.txt", matter_id="SRC")
    body = client.get(f"/v1/documents/{state.doc_id}/source").json()
    assert body["truncated"] is False
    assert "Master Services Agreement".lower() in body["text"].lower()


# ------------------------------------------------------------ corpora / cfg


def test_hf_corpora_default_and_v91_aliases():
    from agent_mailroom.pipeline.hf_corpora import CORPUS_REVISION, CORPUS_REVISION_SHA, resolve_corpus

    assert CORPUS_REVISION == "v9.1"
    assert CORPUS_REVISION_SHA.startswith("ed7576b")
    assert resolve_corpus(None)["slug"] == "docclass-merged"
    for alias in ("v8", "v9", "v9.1", "mailroom-dataset"):
        assert resolve_corpus(alias)["slug"] == "docclass-merged"
    full = resolve_corpus("docclass-merged")
    assert full["splits"] == {"train": 2979, "test": 323}
    assert full["revision"] == "v9.1"


def test_hub_pull_enqueues_without_draining_and_encodes_params(monkeypatch):
    from agent_mailroom.pipeline.bins import inbox_pending
    from agent_mailroom.pipeline.hub import pull_corpus

    monkeypatch.setenv("MAILROOM_SYNC", "0")
    seen = []

    def fake(url):
        seen.append(url)
        return {"rows": [{"row": {"filename": "a.txt", "doc_text": "Dear Sir, demand for payment.", "expected": "correspondence"}}]}

    result = pull_corpus("docclass-pilot", limit=1, config="a&b=c", fetcher=fake)
    assert result["scanned"] == []
    assert len(inbox_pending()) == 1
    assert "config=a%26b%3Dc" in seen[0]


def test_retry_config_keeps_explicit_zero():
    from agent_mailroom.config.loader import _num

    assert _num({"base_delay": 0}, "base_delay", 1.0) == 0.0
    assert _num({}, "base_delay", 1.0) == 1.0
    assert _num({"base_delay": "fast"}, "base_delay", 1.0) == 1.0


def test_version_strings_agree():
    import tomllib

    import agent_mailroom

    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == agent_mailroom.__version__ == "0.3.0"
    assert TestClient(create_app()).app.version == "0.3.0"
    assert "agents/*.json" in (root / "pyproject.toml").read_text(encoding="utf-8")
