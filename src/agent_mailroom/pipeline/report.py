"""Procedural matter-record assembler (reporter LLM retired — llm-mailroom v0.6.0).

Compiles classification + extraction (+ optional arbiter caveats) into a
structured summary. No LLM calls on the happy path.
"""

from __future__ import annotations

import json
from typing import Any


def _fmt_value(value: Any) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return "not stated"
    if isinstance(value, (list, tuple)):
        items = [str(v).strip() for v in value if v not in (None, "")]
        return "; ".join(items) if items else "not stated"
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(value)
    return str(value)


def compile_matter_record(manifest_data: dict[str, Any]) -> dict[str, Any]:
    """Assemble a deterministic matter-record summary from extracted fields."""
    doc_type = manifest_data.get("doc_type", "unknown")
    contract_subtype = manifest_data.get("contract_subtype")
    doc_subclass = manifest_data.get("doc_subclass")
    extracted = manifest_data.get("extracted_data", {}) or {}
    classification_confidence = manifest_data.get("classification_confidence")
    extraction_confidence = manifest_data.get("extraction_confidence")

    cleaned_extracted = {
        k: v
        for k, v in extracted.items()
        if k not in ("confidence", "reasoning", "_report")
    }

    lines = [
        f"Document type: {doc_type}",
        f"Subclass: {doc_subclass or contract_subtype or 'not stated'}",
        f"Classification confidence: {classification_confidence}",
        f"Extraction confidence: {extraction_confidence}",
        "",
        "Extracted fields:",
    ]
    for key in sorted(cleaned_extracted.keys()):
        lines.append(f"- {key}: {_fmt_value(cleaned_extracted[key])}")

    arbiter_decision = manifest_data.get("arbiter_decision")
    arbiter_reasoning = manifest_data.get("arbiter_reasoning")
    if arbiter_decision == "accept_with_caveats" or arbiter_reasoning:
        lines.append("")
        lines.append("Caveats:")
        if arbiter_decision:
            lines.append(f"- arbiter_decision: {arbiter_decision}")
        if arbiter_reasoning:
            lines.append(f"- reasoning: {arbiter_reasoning}")

    judge_verdict = manifest_data.get("judge_verdict")
    if judge_verdict:
        lines.append("")
        lines.append(f"Judge verdict: {judge_verdict}")
        if manifest_data.get("judge_score") is not None:
            lines.append(f"Judge score: {manifest_data.get('judge_score')}")

    summary = "\n".join(lines).strip() + "\n"
    return {
        "summary": summary,
        "doc_type": doc_type,
        "contract_subtype": contract_subtype,
        "doc_subclass": doc_subclass,
        "extracted_data": cleaned_extracted,
        "classification_confidence": classification_confidence,
        "extraction_confidence": extraction_confidence,
        "procedural": True,
    }
