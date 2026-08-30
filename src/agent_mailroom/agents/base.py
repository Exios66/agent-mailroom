from __future__ import annotations

from typing import Any

from agent_mailroom.config.loader import agent_config
from agent_mailroom.llm.client import LLMError, chat_json

PROMPTS: dict[str, str] = {
    "sorter": "You are the mailroom sorter. Classify the document into contract, merger_agreement, corporate_record, correspondence, compliance_filing, insurance_claim, or unknown. Return doc_type, contract_subtype, doc_subclass, confidence (0-1), reasoning.",
    "sorter_reviewer": "You are an independent second-opinion classifier. Ignore any prior label. Return doc_type, confidence, verdict (reviewer_agrees_high|reviewer_agrees_low|reviewer_overrides).",
    "contracts_specialist": "Extract contract fields as JSON matching ContractExtraction.",
    "corporate_records_specialist": "Extract corporate-record fields as JSON matching CorporateRecordExtraction.",
    "correspondence_specialist": "Extract correspondence fields as JSON matching CorrespondenceExtraction.",
    "compliance_specialist": "Extract compliance filing fields as JSON matching ComplianceFilingExtraction.",
    "insurance_claims_specialist": "Extract insurance claim fields as JSON matching InsuranceClaimExtraction.",
    "judge": "Audit extraction completeness. Return verdict (complete|partial|incomplete), score, findings[].",
    "arbiter": "Resolve a failed judge verdict. Return decision (accept_with_caveats|retry_extraction|human_review) and reasoning.",
    "boss": "Adjudicate a matter conflict. Return decision (approved|review) and reasoning.",
    "reporter": "Write a short client-facing matter record. Return {report: string}.",
}


def run_agent(name: str, user: str) -> dict[str, Any]:
    system = PROMPTS.get(name, "You are a mailroom agent. Return JSON.")
    try:
        return chat_json(name, system, user, agent_cfg=agent_config(name))
    except LLMError as exc:
        return {"error": str(exc), "confidence": 0.0, "doc_type": "unknown", "reasoning": str(exc)}
