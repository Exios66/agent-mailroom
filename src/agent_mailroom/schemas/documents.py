from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ContractExtraction(BaseModel):
    # Pared CUAD/MAUD product (llm-mailroom v0.6.0): key entities + clause checklists.
    # Open-ended key_obligations / termination_clauses are no longer extracted.
    document_name: str | None = None
    parties: list[str] = Field(default_factory=list)
    effective_date: str | None = None
    term_length: str | None = None
    governing_law: str | None = None
    contract_value: str | None = None
    renewal_terms: str | None = None
    cuad_family: str | None = None
    merger_consideration: str | None = None
    cuad_clauses: list[str] = Field(default_factory=list)
    maud_clauses: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class CorporateRecordExtraction(BaseModel):
    entity_name: str | None = None
    record_type: str | None = None
    effective_date: str | None = None
    signatories: list[str] = Field(default_factory=list)
    jurisdiction: str | None = None
    filing_number: str | None = None
    intent: str | None = None
    subject_matter: str | None = None
    keywords: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class CorrespondenceExtraction(BaseModel):
    sender: str | None = None
    recipient: str | None = None
    additional_recipients: list[str] = Field(default_factory=list)
    communication_type: str | None = None
    communication_date: str | None = None
    demand_amount: str | None = None
    action_items: list[str] = Field(default_factory=list)
    urgency: str | None = None
    intent: str | None = None
    subject_matter: str | None = None
    keywords: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class ComplianceFilingExtraction(BaseModel):
    filing_type: str | None = None
    regulatory_body: str | None = None
    filing_date: str | None = None
    due_date: str | None = None
    entity_name: str | None = None
    key_requirements: list[str] = Field(default_factory=list)
    status: str | None = None
    reference_number: str | None = None
    confidence: float = 0.0


class InsuranceClaimExtraction(BaseModel):
    claim_number: str | None = None
    policy_number: str | None = None
    insurer: str | None = None
    insured_party: str | None = None
    claim_type: str | None = None
    date_of_loss: str | None = None
    date_filed: str | None = None
    claimed_amount: str | None = None
    adjuster: str | None = None
    damages_description: str | None = None
    coverage_determination: str | None = None
    denial_reasons: list[str] = Field(default_factory=list)
    supporting_documents: list[str] = Field(default_factory=list)
    intent: str | None = None
    subject_matter: str | None = None
    keywords: list[str] = Field(default_factory=list)
    claim_checklist: list[str] = Field(default_factory=list)
    confidence: float = 0.0


EXTRACTION_SCHEMAS: dict[str, type[BaseModel]] = {
    "contract": ContractExtraction,
    "merger_agreement": ContractExtraction,
    "corporate_record": CorporateRecordExtraction,
    "correspondence": CorrespondenceExtraction,
    "compliance_filing": ComplianceFilingExtraction,
    "insurance_claim": InsuranceClaimExtraction,
}


def get_extraction_schema(doc_type: str) -> type[BaseModel]:
    return EXTRACTION_SCHEMAS[doc_type]


def schema_has_substance(data: dict[str, Any]) -> bool:
    for key, value in data.items():
        if key in {"confidence", "reasoning"} or str(key).startswith("_"):
            continue
        if value in (None, "", [], {}, 0, 0.0):
            continue
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and any(str(item).strip() for item in value):
            return True
        if isinstance(value, (int, float)) and value:
            return True
    return False
