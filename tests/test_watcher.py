from fastapi.testclient import TestClient

from agent_mailroom.api.app import create_app
from agent_mailroom.pipeline.bins import enqueue_inbox, inbox_pending
from agent_mailroom.pipeline.watcher import is_running, scan_inbox, start_watcher, status, watcher_enabled
from agent_mailroom.storage.catalog import get_document, list_documents


def test_watcher_stays_off_under_sync():
    assert watcher_enabled() is False
    start_watcher()
    assert is_running() is False
    lamp = status()
    assert lamp["sync"] is True
    assert lamp["lamp"] == "ok"


def test_scan_inbox_claims_sidecar_and_archives(samples):
    raw = (samples / "harborpoint_msa.txt").read_bytes()
    enqueue_inbox(raw, "harborpoint_msa.txt", doc_id="watch-1", matter_id="WATCH", source="drop")
    assert inbox_pending()
    started = scan_inbox()
    assert "watch-1" in started
    assert inbox_pending() == []
    row = get_document("watch-1")
    assert row["stage"] == "archived"
    assert row["original_filename"] == "harborpoint_msa.txt"


def test_scan_inbox_is_idempotent(samples):
    raw = (samples / "acme_claim.txt").read_bytes()
    enqueue_inbox(raw, "acme_claim.txt", doc_id="watch-2", matter_id="WATCH", source="drop")
    scan_inbox()
    scan_inbox()
    matches = [row for row in list_documents() if row["doc_id"] == "watch-2"]
    assert len(matches) == 1
    assert matches[0]["stage"] == "archived"


def test_upload_drains_through_inbox(samples):
    client = TestClient(create_app())
    path = samples / "harborpoint_consent.txt"
    response = client.post(
        "/v1/upload",
        files={"file": (path.name, path.read_bytes(), "text/plain")},
        data={"matter_id": "WATCH-API"},
    )
    assert response.status_code == 202
    doc_id = response.json()["doc_id"]
    row = client.get(f"/v1/status/{doc_id}").json()
    assert row["stage"] == "archived"
    assert inbox_pending() == []
