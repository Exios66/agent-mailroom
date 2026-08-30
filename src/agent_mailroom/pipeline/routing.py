from __future__ import annotations

from agent_mailroom.config.loader import confidence, extractable_types
from agent_mailroom.pipeline.state import RunState

END = "END"
HUMAN = "human_review"


def _conf() -> dict[str, float]:
    return confidence()


def after_classify(state: RunState, *, retry: bool = False) -> str:
    cfg = _conf()
    doc_type = state.doc_type or "unknown"
    score = state.classification_confidence or 0.0
    if doc_type not in extractable_types():
        return HUMAN
    if score >= cfg["high"]:
        return "extract"
    if retry:
        if cfg["low"] <= score < cfg["high"]:
            return "review_classify"
        return HUMAN
    if state.classification_attempts <= cfg["retry_max"]:
        return "retry_classify"
    return HUMAN


def after_review_classify(state: RunState) -> str:
    cfg = _conf()
    doc_type = state.doc_type or "unknown"
    score = state.classification_confidence or 0.0
    if doc_type in extractable_types() and score >= cfg["high"]:
        return "extract"
    return HUMAN


def after_extract(state: RunState) -> str:
    cfg = _conf()
    if state.conflict_detected:
        return "boss_escalation"
    score = state.extraction_confidence or 0.0
    if score >= cfg["low"]:
        if cfg["low"] <= score < cfg["judge_band_high"]:
            return "judge_verify"
        return "compile_report"
    if state.extraction_attempts <= cfg["retry_max"]:
        return "retry_extract"
    return HUMAN


def after_judge(state: RunState) -> str:
    verdict = (state.judge_verdict or "").lower()
    if verdict in {"", "none", "skipped", "complete"}:
        return "compile_report"
    if verdict in {"partial", "incomplete"}:
        return "arbiter"
    return HUMAN


def after_arbiter(state: RunState) -> str:
    decision = (state.arbiter_decision or "").lower()
    if decision == "accept_with_caveats":
        return "compile_report"
    if decision == "retry_extraction" and state.arbiter_retry_count <= 1:
        return "retry_extract"
    return HUMAN


def after_boss(state: RunState) -> str:
    if state.review_decision == "approved":
        return "compile_report"
    return HUMAN
