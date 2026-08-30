from fastapi.testclient import TestClient

from agent_mailroom.api.app import create_app


def test_health_and_meta():
    client = TestClient(create_app())
    health = client.get("/v1/health").json()
    assert health["status"] == "ok"
    meta = client.get("/v1/meta").json()
    assert "contract" in meta["doc_classes"]
    assert "boss" in meta["agents"]


def test_upload_and_status(samples):
    client = TestClient(create_app())
    path = samples / "harborpoint_msa.txt"
    response = client.post(
        "/v1/upload",
        files={"file": (path.name, path.read_bytes(), "text/plain")},
        data={"matter_id": "API-1"},
    )
    assert response.status_code == 200 or response.status_code == 202
    doc_id = response.json()["doc_id"]
    # The worker is a thread; wait briefly via polling the catalog.
    import time

    row = None
    for _ in range(40):
        status = client.get(f"/v1/status/{doc_id}")
        if status.status_code == 200:
            row = status.json()
            if row.get("stage") in {"archived", "review", "failed"}:
                break
        time.sleep(0.05)
    assert row is not None
    floor = client.get("/v1/floor").json()
    assert floor["count"] >= 1
