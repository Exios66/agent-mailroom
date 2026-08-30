from fastapi.testclient import TestClient

from agent_mailroom.api.app import create_app
from agent_mailroom.hive.mailbox import list_inbox
from agent_mailroom.pipeline.topics import (
    launch_queued_topic,
    launch_topic,
    looks_like_document,
    queue_topic,
)


def test_looks_like_document_detects_filings():
    assert looks_like_document("short note") is False
    assert looks_like_document("Dear counsel,\n\nThis is a demand under the agreement.\n" * 4) is True


def test_queue_does_not_deliver_until_launch():
    topic = queue_topic(
        subject="Hold for Monday standup",
        body="Do not start until Michael says so.",
        matter_id="SCRANTON",
    )
    assert topic["status"] == "queued"
    inbox_before = list_inbox("boss")
    assert not any(topic["topic_id"] in str(msg.get("payload")) for msg in inbox_before)

    launched = launch_queued_topic(topic["topic_id"])
    assert launched["status"] in {"assigned", "in_progress"}
    inbox_after = list_inbox("boss")
    assert any("Monday standup" in (msg.get("subject") or "") for msg in inbox_after)


def test_launch_topic_reaches_boss_inbox():
    topic = launch_topic(
        subject="Unpaid Northwind invoices",
        body="Please have Jim pull the demand letter.",
        matter_id="SCRANTON",
    )
    assert topic["status"] in {"assigned", "in_progress"}
    inbox = list_inbox("boss")
    assert any("Northwind" in (msg.get("subject") or "") for msg in inbox)


def test_topics_api_queue_then_launch():
    client = TestClient(create_app())
    queued = client.post(
        "/v1/topics",
        json={
            "subject": "Board consent follow-up",
            "body": "Ask Angela to confirm the audit committee seats.",
            "matter_id": "SCRANTON",
            "action": "queue",
        },
    )
    assert queued.status_code == 200
    topic_id = queued.json()["topic"]["topic_id"]
    assert queued.json()["topic"]["status"] == "queued"

    listed = client.get("/v1/topics").json()
    assert listed["queued"] >= 1
    assert listed["topics"][0]["subject"] == "Board consent follow-up"

    launched = client.post(f"/v1/topics/{topic_id}/launch")
    assert launched.status_code == 200
    assert launched.json()["topic"]["status"] in {"assigned", "in_progress"}

    again = client.post(f"/v1/topics/{topic_id}/launch")
    assert again.status_code == 409

    done = client.post(f"/v1/topics/{topic_id}/complete")
    assert done.status_code == 200
    assert done.json()["status"] == "done"
