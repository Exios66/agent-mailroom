from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

SpeechAct = Literal["request", "inform", "propose", "query", "agree", "refuse", "done"]


class HiveMessage(BaseModel):
    id: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:6])
    conversation: str | None = None
    in_reply_to: str | None = None
    sender: str
    to: str
    act: SpeechAct = "inform"
    subject: str
    body: str = ""
    hops: int = 0
    requires_reply: bool = False
    needs_human: bool = False
    doc_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
