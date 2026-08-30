from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from agent_mailroom.storage.db import connect, init_db, locked


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_topic(
    *,
    subject: str,
    body: str = "",
    matter_id: str = "DEFAULT",
    route_to: str = "boss",
    status: str = "queued",
    doc_id: str | None = None,
) -> dict[str, Any]:
    init_db()
    row = {
        "topic_id": str(uuid4()),
        "matter_id": matter_id,
        "subject": subject.strip(),
        "body": body,
        "route_to": route_to,
        "status": status,
        "doc_id": doc_id,
        "created_at": _now(),
        "updated_at": _now(),
    }
    with locked():
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO topics (
                    topic_id, matter_id, subject, body, route_to, status, doc_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["topic_id"],
                    row["matter_id"],
                    row["subject"],
                    row["body"],
                    row["route_to"],
                    row["status"],
                    row["doc_id"],
                    row["created_at"],
                    row["updated_at"],
                ),
            )
            conn.commit()
    return row


def update_topic(topic_id: str, **fields: Any) -> dict[str, Any] | None:
    init_db()
    fields = {k: v for k, v in fields.items() if v is not None}
    if not fields:
        return get_topic(topic_id)
    fields["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [topic_id]
    with locked():
        with connect() as conn:
            conn.execute(f"UPDATE topics SET {assignments} WHERE topic_id = ?", values)
            conn.commit()
    return get_topic(topic_id)


def get_topic(topic_id: str) -> dict[str, Any] | None:
    init_db()
    with locked():
        with connect() as conn:
            row = conn.execute("SELECT * FROM topics WHERE topic_id = ?", (topic_id,)).fetchone()
    return dict(row) if row else None


def list_topics(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with locked():
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM topics ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]
