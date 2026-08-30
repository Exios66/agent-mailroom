from __future__ import annotations

import os

from agent_mailroom.config.loader import agent_roster
from agent_mailroom.hive.mailbox import deliver, hive_dir, seed_hive
from agent_mailroom.pipeline.bins import enqueue_inbox
from agent_mailroom.pipeline.events import emit
from agent_mailroom.storage.topics import create_topic, get_topic, list_topics, update_topic

LIVE_STATUSES = {"assigned", "in_progress"}


def looks_like_document(body: str) -> bool:
    text = (body or "").strip()
    if len(text) >= 240:
        return True
    needles = (
        "agreement",
        "whereas",
        "claim no",
        "dear ",
        "form 10",
        "resolved,",
        "coverage determination",
    )
    hits = sum(1 for needle in needles if needle in text.lower())
    return hits >= 1 and len(text) >= 80


def _normalize_route(route_to: str) -> str:
    roster = agent_roster()
    return route_to if route_to in roster else "boss"


def queue_topic(
    *,
    subject: str,
    body: str = "",
    matter_id: str = "DEFAULT",
    route_to: str = "boss",
) -> dict:
    """Park a brief. No hive delivery until launch."""
    if not subject.strip():
        raise ValueError("subject required")
    dest = _normalize_route(route_to)
    topic = create_topic(subject=subject, body=body, matter_id=matter_id, route_to=dest, status="queued")
    emit(
        {
            "type": "topic",
            "topic_id": topic["topic_id"],
            "subject": subject,
            "route_to": dest,
            "matter_id": matter_id,
            "status": "queued",
            "action": "queue",
        }
    )
    return topic


def _dispatch(topic: dict, *, ingest: bool | None = None) -> dict:
    dest = _normalize_route(topic["route_to"])
    seed_hive()
    board = hive_dir() / "board.md"
    with board.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {topic['created_at']} — {topic['subject']}\n\n{topic.get('body') or '_no brief_'}\n")

    deliver(
        sender="human",
        to=dest,
        act="request",
        subject=topic["subject"],
        body=topic.get("body") or topic["subject"],
        needs_human=False,
        payload={"topic_id": topic["topic_id"], "matter_id": topic["matter_id"]},
    )
    emit(
        {
            "type": "topic",
            "topic_id": topic["topic_id"],
            "subject": topic["subject"],
            "route_to": dest,
            "matter_id": topic["matter_id"],
            "status": "assigned",
            "action": "launch",
        }
    )

    body = topic.get("body") or ""
    should_ingest = looks_like_document(body) if ingest is None else ingest
    if should_ingest and body.strip():
        enqueue_inbox(
            body.encode("utf-8"),
            "topic.txt",
            doc_id=topic["topic_id"],
            matter_id=topic["matter_id"],
            source="topic",
        )
        if os.environ.get("MAILROOM_SYNC") == "1":
            from agent_mailroom.pipeline.watcher import scan_inbox

            scan_inbox()
        return update_topic(topic["topic_id"], status="in_progress", doc_id=topic["topic_id"]) or topic
    return update_topic(topic["topic_id"], status="assigned") or topic


def launch_topic(
    *,
    subject: str,
    body: str = "",
    matter_id: str = "DEFAULT",
    route_to: str = "boss",
    ingest: bool | None = None,
) -> dict:
    """Create and immediately deliver a brief to a desk."""
    topic = queue_topic(subject=subject, body=body, matter_id=matter_id, route_to=route_to)
    return _dispatch(topic, ingest=ingest)


def launch_queued_topic(topic_id: str, *, ingest: bool | None = None) -> dict:
    topic = get_topic(topic_id)
    if not topic:
        raise KeyError(topic_id)
    if topic["status"] in LIVE_STATUSES:
        raise ValueError("topic already launched")
    if topic["status"] == "done":
        raise ValueError("topic already completed")
    return _dispatch(topic, ingest=ingest)


def complete_topic(topic_id: str) -> dict:
    topic = get_topic(topic_id)
    if not topic:
        raise KeyError(topic_id)
    updated = update_topic(topic_id, status="done")
    emit(
        {
            "type": "topic",
            "topic_id": topic_id,
            "subject": topic["subject"],
            "status": "done",
            "action": "complete",
        }
    )
    return updated or topic


def office_topics() -> list[dict]:
    return list_topics()
