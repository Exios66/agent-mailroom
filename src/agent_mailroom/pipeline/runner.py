from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from agent_mailroom.config.loader import specialist_for
from agent_mailroom.hive.mailbox import deliver
from agent_mailroom.pipeline import nodes, routing
from agent_mailroom.pipeline.bins import (
    archive_dir,
    copy_classified,
    ensure_bins,
    failed_dir,
    move_file,
    processing_dir,
    review_dir,
    write_manifest,
)
from agent_mailroom.observability.tracing import span_context
from agent_mailroom.pipeline.events import emit
from agent_mailroom.pipeline.failures import (
    ABORT_CLASSES,
    aborted_escalation,
    classify_run_failure,
)
from agent_mailroom.pipeline.state import RunState
from agent_mailroom.schemas.manifest import DocumentManifest, PipelineStage
from agent_mailroom.storage.audit import write_audit
from agent_mailroom.storage.catalog import touch_matter, upsert_document


def _abort_or_park(state: RunState, exc: BaseException, soft_prefix: str) -> RunState:
    """Hard LLM/I/O aborts → failed bin with failure_class; soft errors → review."""
    classified = classify_run_failure(exc)
    fc = classified["failure_class"]
    if fc in ABORT_CLASSES - {"schema_error"}:
        return fail_document(state, aborted_escalation(classified), failure_class=fc)
    state.escalation_reason = f"{soft_prefix}: {exc}"
    return park_for_review(state)

STAGE_FOR_NODE = {
    "intake": "intake",
    "classify": "classify",
    "retry_classify": "retry_classify",
    "review_classify": "retry_classify",
    "extract": "extract",
    "retry_extract": "retry_extract",
    "judge_verify": "judge_verify",
    "arbiter": "arbiter",
    "boss_escalation": "boss",
    "human_review": "review",
    "compile_report": "report",
    "catalog_write": "catalog",
    "archive": "archive",
}

MAIL_EDGES = {
    "classify": ("sorter", "inform", "Sorted a document"),
    "retry_classify": ("sorter", "query", "Re-reading the pile"),
    "review_classify": ("sorter_reviewer", "propose", "Second opinion"),
    "extract": (None, "request", "Needs extraction"),
    "retry_extract": (None, "request", "Re-extract please"),
    "judge_verify": ("judge", "query", "Quality check"),
    "arbiter": ("arbiter", "propose", "Arbitration"),
    "boss_escalation": ("boss", "request", "That's what she said — escalate"),
    "human_review": ("boss", "request", "Needs a human"),
    "compile_report": ("reporter", "inform", "Assembling the matter record"),
    "catalog_write": ("archivist", "done", "Writing the catalog"),
    "archive": ("archivist", "done", "Filing it away"),
}


def _persist(state: RunState, *, stage: PipelineStage | None = None) -> DocumentManifest:
    if stage:
        state.stage = stage.value
    manifest = DocumentManifest(
        doc_id=state.doc_id,
        matter_id=state.matter_id,
        original_filename=state.original_filename,
        stage=PipelineStage(state.stage) if state.stage in PipelineStage._value2member_map_ else PipelineStage.PROCESSING,
        graph_node=state.graph_node,
        doc_type=state.doc_type,
        contract_subtype=state.contract_subtype,
        doc_subclass=state.doc_subclass,
        classification_confidence=state.classification_confidence,
        classification_attempts=state.classification_attempts,
        extracted_data=state.extracted_data,
        extraction_confidence=state.extraction_confidence,
        extraction_attempts=state.extraction_attempts,
        report=state.report,
        escalation_reason=state.escalation_reason,
        review_decision=state.review_decision,
        routing_path=state.routing_path,
        judge_verdict=state.judge_verdict,
        judge_score=state.judge_score,
        judge_findings=state.judge_findings,
        arbiter_decision=state.arbiter_decision,
        arbiter_reasoning=state.arbiter_reasoning,
        arbiter_handoff=state.arbiter_handoff,
        arbiter_fields_to_fix=state.arbiter_fields_to_fix,
        arbiter_retry_count=state.arbiter_retry_count,
        failure_class=state.failure_class,
        trace_id=state.doc_id,
    )
    upsert_document(manifest)
    touch_matter(state.matter_id)
    write_manifest(state.doc_id, manifest.model_dump(mode="json"))
    return manifest


def _broadcast(state: RunState, node: str, actor: str) -> None:
    display = STAGE_FOR_NODE.get(node, node)
    emit(
        {
            "type": "pipeline",
            "doc_id": state.doc_id,
            "filename": state.original_filename,
            "matter_id": state.matter_id,
            "stage": display,
            "graph_node": node,
            "actor": actor,
            "doc_type": state.doc_type,
            "classification_confidence": state.classification_confidence,
            "extraction_confidence": state.extraction_confidence,
            "escalation_reason": state.escalation_reason,
            "routing_path": list(state.routing_path),
            "needs_human": node == "human_review",
            "extracted_data": state.extracted_data,
            "report": state.report,
            "judge_verdict": state.judge_verdict,
            "conflict_detected": state.conflict_detected,
        }
    )
    spec = MAIL_EDGES.get(node)
    if not spec:
        return
    to_agent, act, subject = spec
    if to_agent is None:
        to_agent = specialist_for(state.doc_type or "contract")
    sender = "sorter" if node.startswith("extract") else "boss" if node == "human_review" else to_agent
    if node.startswith("extract"):
        sender = "sorter"
    if node == "judge_verify":
        sender = specialist_for(state.doc_type or "contract")
    if node == "compile_report":
        sender = "judge" if state.judge_verdict else specialist_for(state.doc_type or "contract")
    deliver(
        sender=sender,
        to=to_agent,
        act=act,
        subject=f"{subject}: {state.original_filename}",
        body=f"doc_id={state.doc_id} type={state.doc_type}",
        doc_id=state.doc_id,
        needs_human=node == "human_review",
    )


def _audit(state: RunState, event: str, actor: str, detail: dict | None = None) -> None:
    write_audit(
        doc_id=state.doc_id,
        matter_id=state.matter_id,
        event=event,
        actor=actor,
        detail=detail or {},
        filename=state.original_filename,
    )


STAGE_SPAN = {
    "intake": "intake-document",
    "classify": "classify-document",
    "retry_classify": "classify-document",
    "review_classify": "classify-document",
    "extract": "extract-fields",
    "retry_extract": "extract-fields",
    "judge_verify": "judge-verify",
    "arbiter": "arbitrate-verdict",
    "boss_escalation": "adjudicate-conflict",
    "compile_report": "compile-report",
    "archive": "archive-document",
}


def _run_node(state: RunState, node: str, fn) -> RunState:
    span_name = STAGE_SPAN.get(node, node)
    with span_context(state.doc_id, span_name, state=state) as holder:
        result = fn()
        holder["output"] = {
            "stage": result.stage,
            "doc_type": result.doc_type,
            "classification_confidence": result.classification_confidence,
            "extraction_confidence": result.extraction_confidence,
        }
        return result


def run_document(
    file_path: Path,
    *,
    matter_id: str = "DEFAULT",
    doc_id: str | None = None,
    resume: RunState | None = None,
) -> RunState:
    ensure_bins()
    if resume:
        state = resume
    else:
        doc_id = doc_id or str(uuid4())
        dest = processing_dir(doc_id) / file_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if file_path.resolve() != dest.resolve():
            from agent_mailroom.pipeline.bins import inbox_dir, move_file

            if file_path.parent.resolve() == inbox_dir().resolve():
                dest = move_file(file_path, dest.parent, file_path.name)
            else:
                dest.write_bytes(file_path.read_bytes())
        display = file_path.name
        prefix = f"{doc_id}--"
        if display.startswith(prefix):
            display = display[len(prefix) :]
        state = RunState(
            doc_id=doc_id,
            matter_id=matter_id,
            original_filename=display,
            file_path=dest,
        )
        _audit(state, "ingested", "intake", {"path": str(dest)})
        _persist(state, stage=PipelineStage.PROCESSING)
        _broadcast(state, "intake", "intake")

    node = "extract" if state.resume_extraction else "intake"
    safety = 0
    while node and node != routing.END and safety < 40:
        safety += 1
        state.graph_node = node
        state.routing_path.append(STAGE_FOR_NODE.get(node, node))
        actor = _actor(state, node)

        if node == "intake":
            try:
                state = _run_node(state, node, lambda: nodes.node_intake(state))
            except Exception as exc:
                classified = classify_run_failure(exc)
                return fail_document(
                    state,
                    aborted_escalation(classified),
                    failure_class=classified["failure_class"],
                )
            _broadcast(state, node, actor)
            node = "classify"
            continue
        if node in {"classify", "retry_classify"}:
            try:
                state = _run_node(state, node, lambda: nodes.node_classify(state, reviewer=False))
            except Exception as exc:
                return _abort_or_park(state, exc, "classify failed")
            _audit(state, "classified", "sorter", {"doc_type": state.doc_type, "confidence": state.classification_confidence})
            try:
                copy_classified(
                    state.file_path,
                    doc_id=state.doc_id,
                    doc_type=state.doc_type or "unknown",
                    filename=state.original_filename,
                )
            except OSError:
                pass
            _persist(state)
            _broadcast(state, node, actor)
            node = routing.after_classify(state, retry=node == "retry_classify")
            continue
        if node == "review_classify":
            try:
                state = _run_node(state, node, lambda: nodes.node_classify(state, reviewer=True))
            except Exception as exc:
                return _abort_or_park(state, exc, "review-classify failed")
            _broadcast(state, node, actor)
            node = routing.after_review_classify(state)
            continue
        if node in {"extract", "retry_extract"}:
            try:
                state = _run_node(state, node, lambda: nodes.node_extract(state))
            except Exception as exc:
                return _abort_or_park(state, exc, "extract failed")
            _audit(state, "extracted", specialist_for(state.doc_type or "contract"), {"confidence": state.extraction_confidence})
            if state.conflict_detected:
                _audit(state, "conflict_detected", "boss", {"reason": state.escalation_reason})
            _persist(state)
            _broadcast(state, node, actor)
            node = routing.after_extract(state)
            continue
        if node == "judge_verify":
            try:
                state = _run_node(state, node, lambda: nodes.node_judge(state))
            except Exception as exc:
                return _abort_or_park(state, exc, "judge failed")
            _broadcast(state, node, actor)
            node = routing.after_judge(state)
            continue
        if node == "arbiter":
            try:
                state = _run_node(state, node, lambda: nodes.node_arbiter(state))
            except Exception as exc:
                return _abort_or_park(state, exc, "arbiter failed")
            _broadcast(state, node, actor)
            node = routing.after_arbiter(state)
            continue
        if node == "boss_escalation":
            try:
                state = _run_node(state, node, lambda: nodes.node_boss(state))
            except Exception as exc:
                return _abort_or_park(state, exc, "boss failed")
            _audit(state, "boss_adjudicated", "boss", {"decision": state.review_decision})
            _broadcast(state, node, actor)
            node = routing.after_boss(state)
            continue
        if node == "human_review":
            return park_for_review(state)
        if node == "compile_report":
            try:
                state = _run_node(state, node, lambda: nodes.node_report(state))
            except Exception as exc:
                return _abort_or_park(state, exc, "report assemble failed")
            _audit(
                state,
                "report_compiled",
                "reporter",
                {
                    "procedural": True,
                    "judge_verdict": state.judge_verdict,
                    "arbiter_decision": state.arbiter_decision,
                    "arbiter_handoff": state.arbiter_handoff,
                },
            )
            _persist(state)
            _broadcast(state, node, actor)
            node = "catalog_write" if state.report else "human_review"
            continue
        if node == "catalog_write":
            _persist(state)
            _broadcast(state, node, actor)
            node = "archive"
            continue
        if node == "archive":
            return archive_document(state)
        raise RuntimeError(f"unknown node {node}")

    return state


def _actor(state: RunState, node: str) -> str:
    if node in {"extract", "retry_extract"}:
        return specialist_for(state.doc_type or "contract")
    from agent_mailroom.agents.roster import ACTOR_FOR_NODE

    return ACTOR_FOR_NODE.get(node) or node


def park_for_review(state: RunState) -> RunState:
    dest = move_file(state.file_path, review_dir(), f"{state.doc_id}--{state.original_filename}")
    state.file_path = dest
    state.stage = "review"
    state.graph_node = "human_review"
    state.halt = True
    state.escalation_reason = state.escalation_reason or "routed to human review"
    _audit(state, "routed_to_review", "boss", {"reason": state.escalation_reason})
    _persist(state, stage=PipelineStage.REVIEW)
    _broadcast(state, "human_review", "boss")
    return state


def archive_document(state: RunState) -> RunState:
    dest = move_file(
        state.file_path,
        archive_dir(state.matter_id, state.doc_type or "unknown"),
        f"{state.doc_id}--{state.original_filename}",
    )
    state.file_path = dest
    state.stage = "archived"
    state.graph_node = "archive"
    _audit(
        state,
        "archived",
        "archivist",
        {
            "path": str(dest),
            "judge_verdict": state.judge_verdict,
            "arbiter_decision": state.arbiter_decision,
            "arbiter_reasoning": state.arbiter_reasoning,
            "arbiter_handoff": state.arbiter_handoff,
            "arbiter_fields_to_fix": state.arbiter_fields_to_fix,
            "arbiter_retry_count": state.arbiter_retry_count,
        },
    )
    _persist(state, stage=PipelineStage.ARCHIVED)
    _broadcast(state, "archive", "archivist")
    emit(
        {
            "type": "pipeline",
            "doc_id": state.doc_id,
            "filename": state.original_filename,
            "matter_id": state.matter_id,
            "stage": "archived",
            "graph_node": "archive",
            "actor": "archivist",
            "doc_type": state.doc_type,
            "classification_confidence": state.classification_confidence,
            "extraction_confidence": state.extraction_confidence,
            "routing_path": list(state.routing_path),
            "needs_human": False,
            "extracted_data": state.extracted_data,
            "report": state.report,
        }
    )
    return state


def fail_document(state: RunState, reason: str, *, failure_class: str | None = None) -> RunState:
    dest = move_file(state.file_path, failed_dir(), f"{state.doc_id}--{state.original_filename}")
    state.file_path = dest
    state.stage = "failed"
    state.escalation_reason = reason
    if failure_class:
        state.failure_class = failure_class
    elif reason.startswith("run aborted [") and "]" in reason:
        state.failure_class = reason.split("run aborted [", 1)[1].split("]", 1)[0]
    detail = {"reason": reason}
    if state.failure_class:
        detail["failure_class"] = state.failure_class
    detail.update(
        {
            "judge_verdict": state.judge_verdict,
            "arbiter_decision": state.arbiter_decision,
            "arbiter_handoff": state.arbiter_handoff,
        }
    )
    _audit(state, "review_rejected" if not state.failure_class else "run_aborted", "human" if not state.failure_class else "system", detail)
    _persist(state, stage=PipelineStage.FAILED)
    emit(
        {
            "type": "pipeline",
            "doc_id": state.doc_id,
            "filename": state.original_filename,
            "stage": "failed",
            "actor": "system" if state.failure_class else "human",
            "needs_human": False,
            "escalation_reason": reason,
            "failure_class": state.failure_class,
            "routing_path": list(state.routing_path),
        }
    )
    return state


def resume_from_review(doc_id: str, *, doc_type: str | None = None) -> RunState:
    from agent_mailroom.pipeline.bins import load_manifest
    from agent_mailroom.storage.catalog import get_document

    row = get_document(doc_id) or load_manifest(doc_id)
    if not row:
        raise KeyError(doc_id)
    parked = next(review_dir().glob(f"{doc_id}--*"), None)
    if parked is None:
        raise FileNotFoundError(f"no parked review file for {doc_id}")
    work = processing_dir(doc_id) / row["original_filename"]
    work.parent.mkdir(parents=True, exist_ok=True)
    work.write_bytes(parked.read_bytes())
    state = RunState(
        doc_id=doc_id,
        matter_id=row["matter_id"],
        original_filename=row["original_filename"],
        file_path=work,
        doc_type=doc_type or row.get("doc_type"),
        contract_subtype=row.get("contract_subtype"),
        doc_subclass=row.get("doc_subclass"),
        classification_confidence=row.get("classification_confidence"),
        extracted_data=row.get("extracted_data") if isinstance(row.get("extracted_data"), dict) else (
            json.loads(row["extracted_data"]) if row.get("extracted_data") else None
        ),
        resume_extraction=True,
        routing_path=list(row.get("routing_path") or []),
        review_decision="approved",
    )
    nodes.node_intake(state)
    _audit(state, "review_approved", "human", {"doc_type": state.doc_type})
    return run_document(work, matter_id=state.matter_id, resume=state)
