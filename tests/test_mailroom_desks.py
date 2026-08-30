from agent_mailroom.pipeline.bins import classified_dir, locate_document
from agent_mailroom.pipeline.runner import run_document
from agent_mailroom.pipeline.routing import after_extract
from agent_mailroom.pipeline.state import RunState
from agent_mailroom.storage.catalog import get_document
from fastapi.testclient import TestClient

from agent_mailroom.api.app import create_app
from agent_mailroom.storage.db import connect, locked


def test_classified_bin_and_archive_after_run(samples):
    state = run_document(samples / "harborpoint_msa.txt", matter_id="BIN-1")
    assert state.stage == "archived"
    snapshot = classified_dir("contract") / f"{state.doc_id}--{state.original_filename}"
    assert snapshot.is_file()
    loc = locate_document(state.doc_id)
    assert loc["bin"] == "archive"
    assert loc["path"] and loc["path"].is_file()


def test_queue_lists_inbox_before_drain(samples, monkeypatch):
    monkeypatch.delenv("MAILROOM_SYNC", raising=False)
    monkeypatch.setenv("MAILROOM_SYNC", "0")
    monkeypatch.setenv("MAILROOM_WATCHER", "0")
    from agent_mailroom.config import loader

    loader.taxonomy.cache_clear()
    client = TestClient(create_app())
    raw = (samples / "harborpoint_msa.txt").read_bytes()
    response = client.post(
        "/v1/upload",
        files={"file": ("hopper.txt", raw, "text/plain")},
        data={"matter_id": "HOP"},
    )
    assert response.status_code == 202
    queue = client.get("/v1/queue").json()
    assert queue["counts"]["inbox"] >= 1
    assert any(row["filename"] == "hopper.txt" for row in queue["inbox"])


def test_inspect_archive_matters_and_review_record(samples):
    client = TestClient(create_app())
    path = samples / "harborpoint_msa.txt"
    doc_id = client.post(
        "/v1/upload",
        files={"file": (path.name, path.read_bytes(), "text/plain")},
        data={"matter_id": "DESK-1"},
    ).json()["doc_id"]
    inspect = client.get(f"/v1/inspect/{doc_id}").json()
    assert inspect["document"]["stage"] == "archived"
    assert inspect["audit"]["chain_valid"] is True
    assert inspect["source"]["text"]
    archive = client.get("/v1/archive").json()
    assert any(row["doc_id"] == doc_id for row in archive["documents"])
    verify = client.get(f"/v1/archive/{doc_id}/verify").json()
    assert verify["chain_valid"] is True
    matters = client.get("/v1/matters").json()
    assert any(row["matter_id"] == "DESK-1" for row in matters["matters"])


def test_review_record_and_complete(samples):
    state = run_document(samples / "ambiguous_memo.txt", matter_id="REV-1")
    assert state.stage == "review"
    client = TestClient(create_app())
    recorded = client.post(
        f"/v1/review/{state.doc_id}/resolve",
        json={"decision": "approved", "disposition": "record", "notes": "seen", "doc_subclass": "memo"},
    )
    assert recorded.status_code == 200
    assert recorded.json()["status"] == "recorded"
    row = get_document(state.doc_id)
    assert row["doc_subclass"] == "memo"
    source = client.get(f"/v1/documents/{state.doc_id}/source").json()
    assert "text" in source
    assert source.get("readable") is True
    dl = client.get(f"/v1/documents/{state.doc_id}/source", params={"download": "1"})
    assert dl.status_code == 200
    assert dl.content
    done = client.post(
        f"/v1/review/{state.doc_id}/resolve",
        json={
            "decision": "approved",
            "disposition": "complete",
            "doc_type": "correspondence",
            "extracted_data": {
                "sender": "Counsel",
                "recipient": "Client",
                "communication_type": "memo",
                "intent": "clarification",
                "subject_matter": "ambiguous filing",
                "keywords": ["memo"],
                "confidence": 0.95,
            },
        },
    )
    assert done.status_code == 200
    assert done.json()["status"] == "archived"


def test_ops_recover_requeues_stuck_processing(samples):
    import shutil

    from agent_mailroom.pipeline.bins import inbox_dir, processing_dir

    state = run_document(samples / "harborpoint_msa.txt", matter_id="STUCK-1")
    loc = locate_document(state.doc_id)
    assert loc["path"]
    work = processing_dir(state.doc_id) / loc["path"].name
    work.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(loc["path"], work)
    with locked():
        with connect() as conn:
            conn.execute(
                "UPDATE documents SET stage='processing', updated_at=datetime('now','-20 minutes') WHERE doc_id=?",
                (state.doc_id,),
            )
            conn.commit()
    from agent_mailroom.pipeline.ops import recover_stuck

    recovered = recover_stuck(minutes=15)
    assert any(item["doc_id"] == state.doc_id for item in recovered)
    assert get_document(state.doc_id)["stage"] == "inbox"
    assert any(path.name.startswith(state.doc_id) for path in inbox_dir().iterdir() if path.is_file())


def test_judge_toggle(monkeypatch):
    # Global Lane B band under v0.6.0: [0.88, 0.95)
    state = RunState(
        doc_id="j1",
        matter_id="J",
        original_filename="x.txt",
        file_path=__import__("pathlib").Path("."),
        extraction_confidence=0.90,
    )
    monkeypatch.setenv("MAILROOM_JUDGE_VERIFY", "on")
    assert after_extract(state) == "judge_verify"
    monkeypatch.setenv("MAILROOM_JUDGE_VERIFY", "off")
    assert after_extract(state) == "compile_report"


def test_failed_classified_search_and_floor_trays(samples):
    client = TestClient(create_app())
    parked = run_document(samples / "ambiguous_memo.txt", matter_id="TRAY-1")
    assert parked.stage == "review"
    rejected = client.post(
        f"/v1/review/{parked.doc_id}/resolve",
        json={"decision": "rejected", "disposition": "resume", "notes": "nope"},
    )
    assert rejected.json()["status"] == "failed"
    failed = client.get("/v1/failed").json()
    assert any(row["doc_id"] == parked.doc_id for row in failed["documents"])
    filed = run_document(samples / "harborpoint_msa.txt", matter_id="TRAY-2")
    classified = client.get("/v1/classified").json()
    assert classified["count"] >= 1
    assert any(row["doc_id"] == filed.doc_id for row in classified["documents"])
    search = client.get("/v1/search", params={"q": "TRAY-2"}).json()
    assert search["count"] >= 1
    assert any(row["doc_id"] == filed.doc_id for row in search["documents"])
    floor = client.get("/v1/floor").json()
    assert "bins" in floor
    assert floor["bins"]["archive"]["count"] >= 1
    assert floor["bins"]["failed"]["count"] >= 1
    assert any(run.get("tray") == "archive" for run in floor["runs"] if run["doc_id"] == filed.doc_id)
    lookup = client.get("/v1/lookup", params={"doc_id": filed.doc_id}).json()
    assert lookup["document"]["bin"] == "archive"


def test_sweep_and_meta(samples):
    client = TestClient(create_app())
    meta = client.get("/v1/meta").json()
    assert "contract" in meta["stamps"]
    assert "request" in meta["hive_acts"]
    assert "inbox" in meta["trays"]
    assert meta["judge_verify"] is True
    sweep = client.post("/v1/ops/sweep").json()
    assert "escalated" in sweep
    assert "review" in sweep
