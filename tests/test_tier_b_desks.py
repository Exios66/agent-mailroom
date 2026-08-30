from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_mailroom.api.app import create_app
from agent_mailroom.config.loader import subclass_catalog, taxonomy
from agent_mailroom.pipeline.runner import run_document


@pytest.fixture
def client():
    return TestClient(create_app())


def test_meta_subclasses(client):
    meta = client.get("/v1/meta").json()
    assert "subclasses" in meta
    assert "contract" in meta["subclasses"]
    assert "nda" in meta["subclasses"]["contract"]


def test_subclass_catalog_loader():
    catalog = subclass_catalog()
    assert catalog["correspondence"]
    assert any(row.get("subclasses") for row in taxonomy()["doc_classes"])


def test_archive_reconsider_filter(client, samples):
    state = run_document(samples / "harborpoint_msa.txt", matter_id="RECON", doc_id="recon-filter-doc")
    assert state.stage == "archived"
    all_archive = client.get("/v1/archive").json()
    assert all_archive["count"] >= 1
    filtered = client.get("/v1/archive?reconsider=true").json()
    assert filtered["filter"] == "reconsider"
    assert filtered["count"] <= all_archive["count"]


def test_reconsider_endpoint(client, samples):
    run_document(samples / "harborpoint_msa.txt", matter_id="RECON2", doc_id="recon-list-doc")
    payload = client.get("/v1/reconsider").json()
    assert "documents" in payload
    assert isinstance(payload["count"], int)


def test_archive_requeue(client, samples):
    state = run_document(samples / "harborpoint_msa.txt", matter_id="RQ", doc_id="requeue-src-doc")
    result = client.post(f"/v1/archive/{state.doc_id}/requeue").json()
    assert result["status"] == "requeued"
    assert result["doc_id"] != state.doc_id
    # Under MAILROOM_SYNC the watcher drains inbox immediately; confirm the new run exists.
    status = client.get(f"/v1/status/{result['doc_id']}").json()
    assert status["doc_id"] == result["doc_id"]


def test_hive_board(client):
    payload = client.get("/v1/hive").json()
    assert "board" in payload
    assert "content" in payload["board"]
    board = client.get("/v1/hive/board").json()
    assert "content" in board


def test_providers_endpoint(client):
    payload = client.get("/v1/providers").json()
    assert "harnesses" in payload
    assert payload.get("active")
