from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunState:
    doc_id: str
    matter_id: str
    original_filename: str
    file_path: Path
    doc_text: str = ""
    stage: str = "inbox"
    graph_node: str = "ingest"
    doc_type: str | None = None
    contract_subtype: str | None = None
    doc_subclass: str | None = None
    classification_confidence: float | None = None
    classification_attempts: int = 0
    extracted_data: dict[str, Any] | None = None
    extraction_confidence: float | None = None
    extraction_attempts: int = 0
    report: str | None = None
    escalation_reason: str | None = None
    review_decision: str | None = None
    routing_path: list[str] = field(default_factory=list)
    conflict_detected: bool = False
    judge_verdict: str | None = None
    judge_score: float | None = None
    judge_findings: list[str] | None = None
    judge_pass_count: int = 0
    arbiter_decision: str | None = None
    arbiter_reasoning: str | None = None
    arbiter_handoff: str | None = None
    arbiter_fields_to_fix: list[str] | None = None
    arbiter_retry_count: int = 0
    failure_class: str | None = None
    resume_extraction: bool = False
    halt: bool = False
    terminal: str | None = None
    doc_pages: list[str] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "matter_id": self.matter_id,
            "original_filename": self.original_filename,
            "stage": self.stage,
            "graph_node": self.graph_node,
            "doc_type": self.doc_type,
            "contract_subtype": self.contract_subtype,
            "doc_subclass": self.doc_subclass,
            "classification_confidence": self.classification_confidence,
            "extraction_confidence": self.extraction_confidence,
            "extracted_data": self.extracted_data,
            "report": self.report,
            "escalation_reason": self.escalation_reason,
            "review_decision": self.review_decision,
            "routing_path": list(self.routing_path),
            "judge_verdict": self.judge_verdict,
            "judge_score": self.judge_score,
            "arbiter_decision": self.arbiter_decision,
            "arbiter_reasoning": self.arbiter_reasoning,
            "arbiter_handoff": self.arbiter_handoff,
            "arbiter_fields_to_fix": list(self.arbiter_fields_to_fix or []),
            "arbiter_retry_count": self.arbiter_retry_count,
            "failure_class": self.failure_class,
        }
