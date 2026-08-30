from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class PipelineStage(str, Enum):
    INBOX = "inbox"
    PROCESSING = "processing"
    CLASSIFIED = "classified"
    REVIEW = "review"
    FAILED = "failed"
    ARCHIVED = "archived"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentManifest(BaseModel):
    doc_id: str = Field(default_factory=lambda: str(uuid4()))
    matter_id: str = "DEFAULT"
    original_filename: str
    stage: PipelineStage = PipelineStage.INBOX
    graph_node: str | None = None
    doc_type: str | None = None
    contract_subtype: str | None = None
    doc_subclass: str | None = None
    classification_confidence: float | None = None
    classification_attempts: int = 0
    extracted_data: dict[str, Any] | None = None
    extraction_confidence: float | None = None
    extraction_attempts: int = 0
    report: str | None = None
    trace_id: str | None = None
    escalation_reason: str | None = None
    review_decision: str | None = None
    routing_path: list[str] = Field(default_factory=list)
    judge_verdict: str | None = None
    judge_score: float | None = None
    judge_findings: list[str] | None = None
    arbiter_decision: str | None = None
    arbiter_reasoning: str | None = None
    arbiter_retry_count: int = 0
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
