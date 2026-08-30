from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_mailroom.config.loader import agent_roster
from agent_mailroom.pipeline.bins import hive_dir
from agent_mailroom.pipeline.events import emit
from agent_mailroom.schemas.hive import HiveMessage


def _agent_dir(agent: str) -> Path:
    path = hive_dir() / "agents" / agent
    (path / "inbox").mkdir(parents=True, exist_ok=True)
    (path / "outbox").mkdir(parents=True, exist_ok=True)
    (path / "inbox" / ".done").mkdir(parents=True, exist_ok=True)
    return path


def seed_hive() -> None:
    hive = hive_dir()
    protocol = hive / "PROTOCOL.md"
    if not protocol.exists():
        protocol.write_text(
            "# Hive protocol\n\n"
            "Write one JSON message to your outbox. The router delivers it to the recipient inbox.\n"
            "Speech acts: request, inform, propose, query, agree, refuse, done.\n",
            encoding="utf-8",
        )
    registry = {
        name: {
            "role": meta["role"],
            "desk": meta["desk"],
            "character": meta["character"],
            "status": "idle",
        }
        for name, meta in agent_roster().items()
    }
    (hive / "registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    board = hive / "board.md"
    if not board.exists():
        board.write_text("# Blackboard\n\nShared matter notes live here.\n", encoding="utf-8")
    for name in agent_roster():
        folder = _agent_dir(name)
        identity = folder / "identity.md"
        if not identity.exists():
            meta = agent_roster()[name]
            identity.write_text(
                f"# {meta['label']}\n\nRole: {meta['role']}\nDesk: {meta['desk']}\nCharacter: {meta['character']}\n",
                encoding="utf-8",
            )
        memory = folder / "memory.md"
        if not memory.exists():
            memory.write_text("# Memory\n\n", encoding="utf-8")


def deliver(
    *,
    sender: str,
    to: str,
    act: str,
    subject: str,
    body: str = "",
    doc_id: str | None = None,
    needs_human: bool = False,
    payload: dict[str, Any] | None = None,
) -> HiveMessage:
    seed_hive()
    message = HiveMessage(
        sender=sender,
        to=to,
        act=act,  # type: ignore[arg-type]
        subject=subject,
        body=body,
        doc_id=doc_id,
        needs_human=needs_human,
        payload=payload or {},
        requires_reply=act in {"request", "query", "propose"},
    )
    dest = _agent_dir(to) / "inbox" / f"{message.id}.json"
    dest.write_text(message.model_dump_json(indent=2), encoding="utf-8")
    emit(
        {
            "type": "hive",
            "id": message.id,
            "from": sender,
            "to": to,
            "act": act,
            "subject": subject,
            "doc_id": doc_id,
            "needs_human": needs_human,
            "targets": [to],
        }
    )
    return message


def list_inbox(agent: str, limit: int = 20) -> list[dict[str, Any]]:
    folder = _agent_dir(agent) / "inbox"
    files = sorted(folder.glob("*.json"), reverse=True)[:limit]
    out = []
    for path in files:
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def roster_status() -> dict[str, Any]:
    seed_hive()
    registry = json.loads((hive_dir() / "registry.json").read_text(encoding="utf-8"))
    for name in registry:
        inbox = list_inbox(name, limit=50)
        registry[name]["inbox_count"] = len(inbox)
    return registry
