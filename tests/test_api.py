from fastapi.testclient import TestClient

from agent_mailroom.api.app import create_app


def test_health_and_meta():
    client = TestClient(create_app())
    health = client.get("/v1/health").json()
    assert health["status"] == "ok"
    assert health["checks"]["watcher"] == "ok"
    assert health["checks"]["watcher_embedded"] is False
    meta = client.get("/v1/meta").json()
    assert "contract" in meta["doc_classes"]
    assert "boss" in meta["agents"]


def test_ops_status():
    client = TestClient(create_app())
    ops = client.get("/v1/ops/status").json()
    assert ops["sync"] is True
    assert ops["watcher"]["lamp"] == "ok"
    assert "review_queue" in ops
    assert "inbox_pending" in ops
    assert "documents" in ops
    assert "stuck_documents" in ops


def test_upload_and_status(samples):
    client = TestClient(create_app())
    path = samples / "harborpoint_msa.txt"
    response = client.post(
        "/v1/upload",
        files={"file": (path.name, path.read_bytes(), "text/plain")},
        data={"matter_id": "API-1"},
    )
    assert response.status_code == 202
    doc_id = response.json()["doc_id"]
    status = client.get(f"/v1/status/{doc_id}")
    assert status.status_code == 200
    row = status.json()
    assert row.get("stage") == "archived"
    floor = client.get("/v1/floor").json()
    assert floor["count"] >= 1
