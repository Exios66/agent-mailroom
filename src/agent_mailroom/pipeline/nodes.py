from __future__ import annotations

from agent_mailroom.agents.base import run_agent
from agent_mailroom.config.loader import specialist_for
from agent_mailroom.pipeline.conflicts import detect_conflict
from agent_mailroom.pipeline.guards import guard_classification, guard_extraction
from agent_mailroom.pipeline.ingest import read_document
from agent_mailroom.pipeline.state import RunState


def node_ingest(state: RunState) -> RunState:
    state.stage = "processing"
    if not state.doc_text:
        state.doc_text = read_document(state.file_path)
    return state


def node_classify(state: RunState, *, reviewer: bool = False) -> RunState:
    agent = "sorter_reviewer" if reviewer else "sorter"
    try:
        result = run_agent(agent, state.doc_text[:12000])
    except Exception as exc:
        result = {"doc_type": "unknown", "confidence": 0.0, "reasoning": str(exc), "error": str(exc)}
    if result.get("error"):
        state.escalation_reason = str(result["error"])
    state.doc_type = result.get("doc_type") or state.doc_type
    state.contract_subtype = result.get("contract_subtype") or state.contract_subtype
    state.doc_subclass = result.get("doc_subclass") or state.doc_subclass
    conf, flags = guard_classification(state.doc_type, result.get("confidence"))
    state.classification_confidence = conf
    if not reviewer:
        state.classification_attempts += 1
    if flags:
        state.escalation_reason = ",".join(flags)
    state.stage = "classified" if state.doc_type and state.doc_type != "unknown" else "processing"
    return state


def node_extract(state: RunState) -> RunState:
    specialist = specialist_for(state.doc_type or "contract")
    user = f"DOC_TYPE={state.doc_type}\n{state.doc_text[:80000]}"
    try:
        result = run_agent(specialist, user)
    except Exception as exc:
        result = {"confidence": 0.0, "error": str(exc)}
    if result.get("error"):
        state.escalation_reason = str(result["error"])
    conf, flags = guard_extraction(state.doc_type, result, result.get("confidence"))
    state.extracted_data = result
    state.extraction_confidence = conf
    state.extraction_attempts += 1
    if flags:
        state.escalation_reason = ",".join(flags)
    conflict, reason = detect_conflict(state)
    state.conflict_detected = conflict
    if conflict:
        state.escalation_reason = reason
    return state


def node_judge(state: RunState) -> RunState:
    payload = "EXTRACTED_JSON\n" + str(state.extracted_data or {})
    # Prefer a real JSON blob for the mock parser.
    import json

    user = "EXTRACTED_JSON\n" + json.dumps(state.extracted_data or {})
    result = run_agent("judge", user or payload)
    state.judge_verdict = result.get("verdict")
    state.judge_score = result.get("score")
    return state


def node_arbiter(state: RunState) -> RunState:
    result = run_agent("arbiter", f"VERDICT={state.judge_verdict}")
    state.arbiter_decision = result.get("decision")
    if state.arbiter_decision == "retry_extraction":
        state.arbiter_retry_count += 1
    return state


def node_boss(state: RunState) -> RunState:
    result = run_agent("boss", "conflict" if state.conflict_detected else "routine")
    state.review_decision = result.get("decision")
    if state.review_decision == "review":
        state.escalation_reason = result.get("reasoning") or "boss requested review"
    return state


def node_report(state: RunState) -> RunState:
    result = run_agent("reporter", f"DOC_TYPE={state.doc_type}\n{state.extracted_data}")
    state.report = result.get("report") or str(result)
    return state
