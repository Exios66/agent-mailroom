from __future__ import annotations

import json

from agent_mailroom.agents.base import run_agent
from agent_mailroom.config.loader import agent_config, specialist_for
from agent_mailroom.pipeline.conflicts import detect_conflict
from agent_mailroom.pipeline.guards import guard_classification, guard_extraction
from agent_mailroom.pipeline.intake import read_document
from agent_mailroom.llm.vision import render_document_pages
from agent_mailroom.pipeline.report import compile_matter_record
from agent_mailroom.pipeline.state import RunState

# LLM / transport failures are NOT caught here: they propagate to the runner,
# whose _abort_or_park sends hard aborts (auth, timeout, rate limit, …) to the
# failed bin with a failure_class and soft ones to review. The nodes used to
# swallow every exception into ``doc_type=unknown`` / an error dict stored as
# ``extracted_data``, so outages looked like classification misses.


def _input_budget(agent: str, default: int) -> int:
    return int(agent_config(agent).get("max_input_chars") or default)


def node_intake(state: RunState) -> RunState:
    state.stage = "processing"
    if not state.doc_text:
        state.doc_text = read_document(state.file_path)
    if not state.doc_pages:
        state.doc_pages = render_document_pages(state.file_path)
    return state


def node_classify(state: RunState, *, reviewer: bool = False) -> RunState:
    agent = "sorter_reviewer" if reviewer else "sorter"
    result = run_agent(agent, state.doc_text[: _input_budget(agent, 12000)])
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
    header = f"DOC_TYPE={state.doc_type}"
    if state.arbiter_fields_to_fix:
        # retry_extract: tell the specialist what the arbiter wants fixed.
        header += "\nFIELDS_TO_FIX=" + ", ".join(state.arbiter_fields_to_fix)
        if state.judge_findings:
            header += "\nJUDGE_FINDINGS=" + "; ".join(state.judge_findings)
    user = f"{header}\n{state.doc_text[: _input_budget(specialist, 80000)]}"
    result = run_agent(specialist, user)
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
    # The judge must see the source: it used to receive only the extracted
    # JSON, so "complete" meant "looks plausible", not "matches the document".
    user = (
        f"DOC_TYPE={state.doc_type}\n"
        "EXTRACTED_JSON\n" + json.dumps(state.extracted_data or {})
        + "\n\nSOURCE_TEXT\n" + state.doc_text[: _input_budget("judge", 60000)]
    )
    result = run_agent("judge", user)
    verdict = result.get("verdict")
    state.judge_verdict = str(verdict).strip().lower() if verdict else "judge_error"
    score = result.get("score")
    state.judge_score = score if isinstance(score, (int, float)) and not isinstance(score, bool) else None
    findings = result.get("findings")
    state.judge_findings = [str(f) for f in findings] if isinstance(findings, list) else None
    fields = result.get("fields_to_fix")
    if isinstance(fields, list) and fields:
        state.arbiter_fields_to_fix = [str(f) for f in fields]
    state.judge_pass_count += 1
    return state


def node_arbiter(state: RunState) -> RunState:
    user = (
        f"VERDICT={state.judge_verdict}\n"
        f"DOC_TYPE={state.doc_type}\n"
        f"JUDGE_SCORE={state.judge_score}\n"
        f"JUDGE_FINDINGS={json.dumps(state.judge_findings or [])}\n"
        f"EXTRACTION_ATTEMPTS={state.extraction_attempts}\n"
        "EXTRACTED_JSON\n" + json.dumps(state.extracted_data or {})
        + "\n\nSOURCE_TEXT\n" + state.doc_text[: _input_budget("arbiter", 100000)]
    )
    result = run_agent("arbiter", user)
    state.arbiter_decision = result.get("decision")
    state.arbiter_reasoning = result.get("reasoning")
    handoff = result.get("handoff_summary") or result.get("handoff")
    state.arbiter_handoff = str(handoff) if handoff else None
    fields = result.get("fields_to_fix")
    if isinstance(fields, list):
        state.arbiter_fields_to_fix = [str(item) for item in fields]
    elif isinstance(fields, str) and fields.strip():
        state.arbiter_fields_to_fix = [fields.strip()]
    if state.arbiter_decision == "retry_extraction":
        state.arbiter_retry_count += 1
    return state


def node_boss(state: RunState) -> RunState:
    user = (
        f"CONFLICT={'yes' if state.conflict_detected else 'no'}\n"
        f"REASON={state.escalation_reason or ''}\n"
        f"MATTER={state.matter_id}\n"
        f"DOC_TYPE={state.doc_type}\n"
        "EXTRACTED_JSON\n" + json.dumps(state.extracted_data or {})
    )
    result = run_agent("boss", user)
    state.review_decision = result.get("decision")
    if state.review_decision != "approved":
        state.escalation_reason = result.get("reasoning") or "boss requested review"
    return state


def node_report(state: RunState) -> RunState:
    """Procedural matter-record assemble — no reporter LLM (v0.6.0)."""
    record = compile_matter_record(
        {
            "doc_type": state.doc_type,
            "contract_subtype": state.contract_subtype,
            "doc_subclass": state.doc_subclass,
            "extracted_data": state.extracted_data or {},
            "classification_confidence": state.classification_confidence,
            "extraction_confidence": state.extraction_confidence,
            "arbiter_decision": state.arbiter_decision,
            "arbiter_reasoning": state.arbiter_reasoning,
            "arbiter_handoff": state.arbiter_handoff,
            "judge_verdict": state.judge_verdict,
            "judge_score": state.judge_score,
        }
    )
    state.report = record["summary"]
    if isinstance(state.extracted_data, dict):
        state.extracted_data = {**state.extracted_data, "_report": record}
    elif state.extracted_data is None:
        state.extracted_data = {"_report": record}
    return state
