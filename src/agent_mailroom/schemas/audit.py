from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    doc_id: str
    matter_id: str
    event: str
    actor: str
    detail: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str = ""
    entry_hash: str = ""
    seq: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
