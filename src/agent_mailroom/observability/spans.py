from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from agent_mailroom.storage.db import connect, locked


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_seq(doc_id: str) -> int:
    with locked():
        with connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM pipeline_spans WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            return int(row["n"])


def record_span(
    doc_id: str,
    name: str,
    *,
    observation_type: str = "span",
    input_data: dict[str, Any] | None = None,
    output_data: dict[str, Any] | None = None,
    latency_ms: float | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> str:
    span_id = str(uuid.uuid4())
    started = started_at or _utcnow()
    ended = ended_at or _utcnow()
    seq = _next_seq(doc_id)
    with locked():
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO pipeline_spans
                (span_id, doc_id, name, observation_type, started_at, ended_at,
                 latency_ms, input_json, output_json, seq)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    span_id,
                    doc_id,
                    name,
                    observation_type,
                    started,
                    ended,
                    latency_ms,
                    json.dumps(input_data) if input_data is not None else None,
                    json.dumps(output_data) if output_data is not None else None,
                    seq,
                ),
            )
            conn.commit()
    return span_id


@contextmanager
def span(
    doc_id: str,
    name: str,
    *,
    observation_type: str = "span",
    input_data: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    started = datetime.now(timezone.utc)
    holder: dict[str, Any] = {"output": None}
    try:
        yield holder
    finally:
        ended = datetime.now(timezone.utc)
        latency_ms = (ended - started).total_seconds() * 1000.0
        record_span(
            doc_id,
            name,
            observation_type=observation_type,
            input_data=input_data,
            output_data=holder.get("output"),
            latency_ms=latency_ms,
            started_at=started.isoformat(),
            ended_at=ended.isoformat(),
        )


def list_spans(doc_id: str) -> list[dict[str, Any]]:
    with locked():
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT span_id, doc_id, name, observation_type, started_at, ended_at,
                       latency_ms, input_json, output_json, seq
                FROM pipeline_spans
                WHERE doc_id = ?
                ORDER BY seq ASC
                """,
                (doc_id,),
            ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in ("input_json", "output_json"):
            raw = item.pop(key, None)
            if raw:
                try:
                    item[key.replace("_json", "")] = json.loads(raw)
                except json.JSONDecodeError:
                    item[key.replace("_json", "")] = raw
            else:
                item[key.replace("_json", "")] = None
        out.append(item)
    return out
