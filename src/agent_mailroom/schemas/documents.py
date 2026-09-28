"""Extraction schemas — mirror llm-mailroom 0.7.1 @959bb0b ``schemas/documents.py``.

``compliance_filing`` is gone upstream (no schema, taxonomy row or
specialist); ``merger_agreement`` has its own ``MergerAgreementExtraction``.
Money fields are floats upstream; the before-validator here accepts the
"$12,500.00" strings models actually emit instead of failing the whole
extraction as schema-invalid.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

_MONEY_CLEAN = re.compile(r"[,$€£\s]|USD|EUR|GBP", re.I)


def _money(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _MONEY_CLEAN.sub("", str(value))
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        amount = float(text)
    except ValueError:
        return None
    return -amount if negative else amount


class ContractExtraction(BaseModel):
    # Pared CUAD/MAUD product: key entities + clause checklists.
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
    reasoning: dict | None = None


class MergerAgreementExtraction(BaseModel):
    # MAUD (LegalBench) — dedicated merger_agreement_specialist.
    document_name: str | None = None
    parties: list[str] = Field(default_factory=list)
    effective_date: str | None = None
    effective_time: str | None = None
    governing_law: str | None = None
    merger_consideration: str | None = None
    maud_clauses: list[str] = Field(default_factory=list)
    intent: str | None = None
    subject_matter: str | None = None
    keywords: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reasoning: dict | None = None


class CorporateRecordExtraction(BaseModel):
    entity_name: str = ""
    record_type: str = ""
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
    communication_type: str = ""
    communication_date: str | None = None
    demand_amount: float | None = None
    action_items: list[str] = Field(default_factory=list)
    urgency: str = ""
    intent: str | None = None
    subject_matter: str | None = None
    keywords: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    _demand = field_validator("demand_amount", mode="before")(classmethod(lambda cls, v: _money(v)))


class InsuranceClaimExtraction(BaseModel):
    claim_number: str | None = None
    policy_number: str | None = None
    insurer: str = ""
    insured_party: str = ""
    claim_type: str = ""
    date_of_loss: str | None = None
    date_filed: str | None = None
    claimed_amount: float | None = None
    adjuster: str | None = None
    damages_description: str = ""
    coverage_determination: str = ""
    denial_reasons: list[str] = Field(default_factory=list)
    supporting_documents: list[str] = Field(default_factory=list)
    intent: str | None = None
    subject_matter: str | None = None
    keywords: list[str] = Field(default_factory=list)
    claim_checklist: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    _claimed = field_validator("claimed_amount", mode="before")(classmethod(lambda cls, v: _money(v)))


EXTRACTION_SCHEMAS: dict[str, type[BaseModel]] = {
    "contract": ContractExtraction,
    "merger_agreement": MergerAgreementExtraction,
    "corporate_record": CorporateRecordExtraction,
    "correspondence": CorrespondenceExtraction,
    "insurance_claim": InsuranceClaimExtraction,
}

# Retired / alias labels a sorter may still emit.
SCHEMA_ALIASES: dict[str, str] = {}


def get_extraction_schema(doc_type: str | None) -> type[BaseModel] | None:
    """Schema for a doc type, or None (an unknown or retired type used to
    raise ``KeyError`` from inside the pipeline)."""
    if not doc_type:
        return None
    key = SCHEMA_ALIASES.get(doc_type, doc_type)
    return EXTRACTION_SCHEMAS.get(key)


def schema_has_substance(data: dict[str, Any]) -> bool:
    for key, value in data.items():
        if key in {"confidence", "reasoning"} or str(key).startswith("_"):
            continue
        if value in (None, "", [], {}):
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and any(str(item).strip() for item in value):
            return True
        if isinstance(value, (int, float)):
            # A stated $0 is a value, not absence (llm-mailroom doctrine).
            return True
    return False
