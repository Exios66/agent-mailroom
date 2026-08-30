from __future__ import annotations

import os

from agent_mailroom.config.loader import confidence, extractable_types
from agent_mailroom.pipeline.state import RunState

END = "END"
HUMAN = "human_review"


def judge_enabled() -> bool:
    raw = os.environ.get("MAILROOM_JUDGE_VERIFY", "on").strip().lower()
    return raw not in {"0", "off", "false", "no"}


def _conf(state: RunState) -> dict:
    return confidence(state.doc_type)


def after_classify(state: RunState, *, retry: bool = False) -> str:
    cfg = _conf(state)
    doc_type = state.doc_type or "unknown"
    score = state.classification_confidence or 0.0
    retry_max = int(cfg.get("retry_max", 2) or 2)
    if doc_type not in extractable_types():
        return HUMAN
    if score >= cfg["high"]:
        return "extract"
    if retry:
        if cfg["low"] <= score < cfg["high"]:
            return "review_classify"
        return HUMAN
    if state.classification_attempts <= retry_max:
        return "retry_classify"
    return HUMAN


def after_review_classify(state: RunState) -> str:
    cfg = _conf(state)
    doc_type = state.doc_type or "unknown"
    score = state.classification_confidence or 0.0
    if doc_type in extractable_types() and score >= cfg["high"]:
        return "extract"
    return HUMAN


def after_extract(state: RunState) -> str:
    cfg = _conf(state)
    retry_max = int(cfg.get("retry_max", 2) or 2)
    if state.conflict_detected:
        return "boss_escalation"
    score = state.extraction_confidence or 0.0
    if score >= cfg["low"]:
        band_high = float(cfg.get("judge_band_high", 0.95))
        if cfg["low"] <= score < band_high and judge_enabled():
            return "judge_verify"
        return "compile_report"
    if state.extraction_attempts <= retry_max:
        return "retry_extract"
    return HUMAN


def after_judge(state: RunState) -> str:
    verdict = (state.judge_verdict or "").lower()
    if verdict in {"", "none", "skipped", "complete"}:
        return "compile_report"
    cfg = _conf(state)
    max_passes = int(cfg.get("judge_max_passes", 3) or 3)
    if state.judge_pass_count >= max_passes and verdict in {"partial", "incomplete"}:
        return HUMAN
    if verdict in {"partial", "incomplete"}:
        return "arbiter"
    return HUMAN


def after_arbiter(state: RunState) -> str:
    decision = (state.arbiter_decision or "").lower()
    if decision == "accept_with_caveats":
        return "compile_report"
    cfg = _conf(state)
    arbiter_retry_max = int(cfg.get("arbiter_retry_max", 2) or 2)
    if decision == "retry_extraction" and state.arbiter_retry_count <= arbiter_retry_max:
        return "retry_extract"
    return HUMAN


def after_boss(state: RunState) -> str:
    if state.review_decision == "approved":
        return "compile_report"
    return HUMAN
