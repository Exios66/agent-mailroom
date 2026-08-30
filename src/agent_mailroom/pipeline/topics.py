from __future__ import annotations

from pathlib import Path

from agent_mailroom.config.loader import agent_roster
from agent_mailroom.hive.mailbox import deliver, hive_dir, seed_hive
from agent_mailroom.pipeline.bins import inbox_dir
from agent_mailroom.pipeline.events import emit
from agent_mailroom.pipeline.runner import run_document
from agent_mailroom.storage.topics import create_topic, list_topics, update_topic


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


def launch_topic(
    *,
    subject: str,
    body: str = "",
    matter_id: str = "DEFAULT",
    route_to: str = "boss",
    ingest: bool | None = None,
) -> dict:
    if not subject.strip():
        raise ValueError("subject required")
    roster = agent_roster()
    dest = route_to if route_to in roster else "boss"
    topic = create_topic(subject=subject, body=body, matter_id=matter_id, route_to=dest, status="queued")
    seed_hive()
    board = hive_dir() / "board.md"
    with board.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {topic['created_at']} — {subject}\n\n{body or '_no brief_'}\n")

    deliver(
        sender="human",
        to=dest,
        act="request",
        subject=subject,
        body=body or subject,
        needs_human=False,
        payload={"topic_id": topic["topic_id"], "matter_id": matter_id},
    )
    emit(
        {
            "type": "topic",
            "topic_id": topic["topic_id"],
            "subject": subject,
            "route_to": dest,
            "matter_id": matter_id,
            "status": "queued",
        }
    )

    should_ingest = looks_like_document(body) if ingest is None else ingest
    if should_ingest and body.strip():
        doc_id = topic["topic_id"]
        dest_path = inbox_dir() / f"{doc_id}--topic.txt"
        dest_path.write_text(body, encoding="utf-8")
        state = run_document(Path(dest_path), matter_id=matter_id, doc_id=doc_id)
        topic = update_topic(topic["topic_id"], status="in_progress", doc_id=state.doc_id) or topic
    else:
        topic = update_topic(topic["topic_id"], status="assigned") or topic
    return topic


def office_topics() -> list[dict]:
    return list_topics()
