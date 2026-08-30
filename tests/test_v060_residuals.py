"""llm-mailroom v0.6.0 residual contract: failures, Complete validation, tokens, stale requeue."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_mailroom.api.app import create_app
from agent_mailroom.api.routes import active_api_tokens
from agent_mailroom.pipeline.bins import enqueue_inbox, inbox_dir, requeue_stale_processing
from agent_mailroom.pipeline.failures import (
    IO_ERROR,
    LLM_AUTH,
    LLM_RATE_LIMIT,
    LLM_TIMEOUT,
    RUN_BUDGET,
    UNEXPECTED,
    classify_run_failure,
)
from agent_mailroom.pipeline.review_resolve import (
    resolve_complete_extracted,
    validate_operator_extraction,
)
from agent_mailroom.pipeline.runner import run_document
from agent_mailroom.storage.catalog import get_document


def test_classify_run_failure_classes():
    class _Http(Exception):
        def __init__(self, status_code: int, msg: str):
            super().__init__(msg)
            self.status_code = status_code

    assert classify_run_failure(_Http(401, "invalid api key"))["failure_class"] == LLM_AUTH
    assert classify_run_failure(_Http(429, "rate limit"))["failure_class"] == LLM_RATE_LIMIT
    assert classify_run_failure(TimeoutError("openrouter timed out"))["failure_class"] == LLM_TIMEOUT
    assert classify_run_failure(PermissionError("/data/inbox"))["failure_class"] == IO_ERROR
    assert classify_run_failure(FileNotFoundError("missing.pdf"))["failure_class"] == IO_ERROR
    assert classify_run_failure(RuntimeError("boom"))["failure_class"] == UNEXPECTED
    assert classify_run_failure(RuntimeError("run budget exceeded"))["failure_class"] == RUN_BUDGET


def test_validate_operator_extraction_accepts_matching_schema():
    out = validate_operator_extraction(
        "insurance_claim",
        {"claim_number": "CL-1", "intent": "fnol", "subject_matter": "water", "keywords": ["fnol"]},
    )
    assert out["claim_number"] == "CL-1"


def test_validate_operator_extraction_rejects_foreign_fields():
    try:
        validate_operator_extraction(
            "contract",
            {
                "document_name": "MSA",
                "parties": ["A", "B"],
                "sender": "should-not-be-here",
                "cuad_clauses": ["Governing Law"],
            },
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "sender" in str(exc)


def test_resolve_complete_extracted_falls_back_to_parked():
    assert resolve_complete_extracted({}, {"claim_number": "CL-1"}) == {"claim_number": "CL-1"}
    assert resolve_complete_extracted({"a": 2}, {"a": 1}) == {"a": 2}
    try:
        resolve_complete_extracted(None, None)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_complete_rejects_foreign_specialist_fields(samples):
    state = run_document(samples / "ambiguous_memo.txt", matter_id="COMPLETE-X")
    assert state.stage == "review"
    client = TestClient(create_app())
    bad = client.post(
        f"/v1/review/{state.doc_id}/resolve",
        json={
            "decision": "approved",
            "disposition": "complete",
            "doc_type": "contract",
            "extracted_data": {
                "document_name": "X",
                "parties": ["A"],
                "sender": "foreign",
                "cuad_clauses": ["Governing Law"],
            },
        },
    )
    assert bad.status_code == 400
    assert "sender" in bad.json()["detail"]


def test_complete_without_extracted_data_400(samples):
    state = run_document(samples / "ambiguous_memo.txt", matter_id="COMPLETE-EMPTY")
    client = TestClient(create_app())
    # Clear any parked extraction so Complete has nothing to fall back on.
    from agent_mailroom.storage.db import connect, locked

    with locked():
        with connect() as conn:
            conn.execute("UPDATE documents SET extracted_data=NULL WHERE doc_id=?", (state.doc_id,))
            conn.commit()
    resp = client.post(
        f"/v1/review/{state.doc_id}/resolve",
        json={"decision": "approved", "disposition": "complete", "doc_type": "correspondence"},
    )
    assert resp.status_code == 400


def test_complete_rejected_decision_400(samples):
    state = run_document(samples / "ambiguous_memo.txt", matter_id="COMPLETE-REJ")
    client = TestClient(create_app())
    resp = client.post(
        f"/v1/review/{state.doc_id}/resolve",
        json={"decision": "rejected", "disposition": "complete", "notes": "nope"},
    )
    assert resp.status_code == 400


def test_active_api_tokens_rotation(monkeypatch):
    monkeypatch.setenv("MAILROOM_API_TOKEN", "primary")
    monkeypatch.setenv("MAILROOM_API_TOKENS", "rot-a, rot-b")
    monkeypatch.setenv("MAILROOM_API_TOKEN_REVOKED", "rot-b,primary")
    tokens = active_api_tokens()
    assert tokens == {"rot-a"}
    client = TestClient(create_app())
    denied = client.get("/v1/queue", headers={"Authorization": "Bearer primary"})
    assert denied.status_code == 401
    ok = client.get("/v1/queue", headers={"Authorization": "Bearer rot-a"})
    assert ok.status_code == 200
    assert client.get("/v1/meta").json()["auth_required"] is True


def test_requeue_stale_processing_idempotent():
    raw = b"same-bytes-payload"
    path = enqueue_inbox(raw, "claim.txt", doc_id="stale-1", matter_id="S", source="drop")
    from agent_mailroom.pipeline.bins import processing_dir

    stranded = processing_dir("stale-1") / path.name
    stranded.parent.mkdir(parents=True, exist_ok=True)
    stranded.write_bytes(raw)
    dest = requeue_stale_processing(stranded)
    assert dest.exists()
    assert not stranded.exists()
    stranded2 = processing_dir("stale-1") / path.name
    stranded2.write_bytes(raw)
    dest2 = requeue_stale_processing(stranded2)
    assert dest2 == dest
    inbox_names = [p.name for p in inbox_dir().iterdir() if p.is_file() and not p.name.endswith(".meta")]
    assert len(inbox_names) == 1
