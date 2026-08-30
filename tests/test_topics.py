from fastapi.testclient import TestClient

from agent_mailroom.api.app import create_app
from agent_mailroom.hive.mailbox import list_inbox
from agent_mailroom.pipeline.topics import launch_topic, looks_like_document


def test_looks_like_document_detects_filings():
    assert looks_like_document("short note") is False
    assert looks_like_document("Dear counsel,\n\nThis is a demand under the agreement.\n" * 4) is True


def test_launch_topic_reaches_boss_inbox():
    topic = launch_topic(subject="Unpaid Northwind invoices", body="Please have Jim pull the demand letter.", matter_id="SCRANTON")
    assert topic["status"] in {"assigned", "in_progress", "queued"}
    inbox = list_inbox("boss")
    assert any("Northwind" in (msg.get("subject") or "") for msg in inbox)


def test_topics_api():
    client = TestClient(create_app())
    response = client.post(
        "/v1/topics",
        json={"subject": "Board consent follow-up", "body": "Ask Angela to confirm the audit committee seats.", "matter_id": "SCRANTON"},
    )
    assert response.status_code == 200
    listed = client.get("/v1/topics").json()
    assert listed["count"] >= 1
    assert listed["topics"][0]["subject"] == "Board consent follow-up"
