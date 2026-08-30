from __future__ import annotations

import re
from typing import Any


def _norm(text: str) -> str:
    return text.lower()


def classify(text: str) -> dict[str, Any]:
    blob = _norm(text)
    rules = [
        (
            "insurance_claim",
            0.99,
            ("claim no", "coverage determination", "policy no", "date of loss", "adjuster"),
        ),
        (
            "correspondence",
            0.97,
            ("dear ", "demand for payment", "very truly yours", "notice of breach"),
        ),
        (
            "corporate_record",
            0.97,
            ("board of directors", "resolved,", "written consent", "bylaws"),
        ),
        (
            "compliance_filing",
            0.98,
            ("form 10-k", "form 10-q", "securities and exchange", "item 1a"),
        ),
        (
            "merger_agreement",
            0.99,
            ("agreement and plan of merger", "surviving corporation", "merger consideration"),
        ),
        (
            "contract",
            0.99,
            ("master services agreement", "now, therefore", "governing law", "in witness whereof"),
        ),
    ]
    for doc_type, conf, needles in rules:
        hits = sum(1 for needle in needles if needle in blob)
        if hits >= 2 or (hits == 1 and doc_type in {"insurance_claim", "correspondence"}):
            return {
                "doc_type": doc_type,
                "doc_subclass": None,
                "contract_subtype": "msa" if doc_type == "contract" else None,
                "confidence": conf,
                "reasoning": f"mock rule hits={hits} type={doc_type}",
            }
    if "ambiguous" in blob or ("memo" in blob and "contract" in blob and "claim" in blob):
        return {
            "doc_type": "correspondence",
            "confidence": 0.88,
            "reasoning": "mixed topics — medium band",
        }
    return {"doc_type": "unknown", "confidence": 0.4, "reasoning": "no taxonomy match"}


def _first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.I | re.M)
    return match.group(1).strip() if match else None


def extract(doc_type: str, text: str) -> dict[str, Any]:
    if doc_type in {"contract", "merger_agreement"}:
        return {
            "document_name": _first(r"^(.*agreement.*)$", text.splitlines()[0] if text else "")
            or "Master Services Agreement",
            "parties": [
                p
                for p in re.findall(
                    r"\b([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)+(?: Inc\.| LLC| Corporation)?)",
                    text,
                )[:4]
            ],
            "effective_date": _first(r"(?:dated|effective as of)\s+([A-Z][a-z]+ \d{1,2}, \d{4})", text),
            "governing_law": _first(r"(Delaware|Wisconsin|New York)", text),
            "cuad_clauses": [
                "Governing Law: Delaware",
                "Payment: Net 30",
            ],
            "maud_clauses": [] if doc_type == "contract" else ["Merger Consideration: mixed"],
            "confidence": 0.98,
        }
    if doc_type == "corporate_record":
        return {
            "entity_name": _first(r"OF\n([A-Z][A-Z0-9 .,&'-]+)", text)
            or _first(r"of\n([A-Za-z0-9 .,&'-]+)", text)
            or "HarborPoint Holdings, Inc.",
            "record_type": "board_consent" if "consent" in text.lower() else "corporate_record",
            "effective_date": _first(r"as of the (\d{1,2}(?:st|nd|rd|th)? day of [A-Za-z]+, \d{4})", text),
            "signatories": re.findall(r"/s/\s+([A-Za-z .]+)", text)[:5],
            "jurisdiction": _first(r"(Delaware|Wisconsin|New York)", text),
            "intent": "authorize_transaction",
            "subject_matter": "Approve Master Services Agreement and Audit Committee",
            "keywords": ["consent", "audit committee", "msa"],
            "confidence": 0.96,
        }
    if doc_type == "correspondence":
        return {
            "sender": _first(r"This firm represents ([^.]+)", text) or "Northwind Logistics Corporation",
            "recipient": _first(r"Attn:\s+(.+)", text) or "General Counsel",
            "communication_type": "demand_letter" if "demand" in text.lower() else "letter",
            "communication_date": _first(
                r"^(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}",
                text,
            ),
            "demand_amount": _first(r"\$([0-9,]+\.\d{2})", text),
            "action_items": ["Cure breach within ten days", "Pay outstanding invoices"],
            "urgency": "high",
            "intent": "demand_cure",
            "subject_matter": "Unpaid invoices and material breach",
            "keywords": ["demand", "breach", "invoices"],
            "confidence": 0.94,
        }
    if doc_type == "compliance_filing":
        return {
            "filing_type": _first(r"(Form 10-K|Form 10-Q|Form 8-K|S-1)", text) or "Form 10-K",
            "regulatory_body": "SEC",
            "entity_name": _first(r"([A-Z][A-Za-z0-9 .,&]+(?:, Inc\.))", text),
            "status": "filed",
            "key_requirements": ["Risk factors", "Financial statements"],
            "confidence": 0.96,
        }
    if doc_type == "insurance_claim":
        return {
            "claim_number": _first(r"Claim No\.:\s*([A-Z0-9-]+)", text),
            "policy_number": _first(r"Policy No\.:\s*([A-Z0-9-]+)", text),
            "insurer": _first(r"Insurer:\s*(.+)", text) or "Acme Insurance Company",
            "insured_party": _first(r"Insured:\s*(.+)", text),
            "claim_type": _first(r"Claim Type:\s*(.+)", text),
            "date_of_loss": _first(r"Date of Loss:\s*(.+)", text),
            "date_filed": _first(r"Date Filed:\s*(.+)", text),
            "claimed_amount": _first(r"Claimed Amount:\s*(\$[0-9,]+\.\d{2})", text),
            "adjuster": _first(r"Adjuster:\s*(.+)", text),
            "coverage_determination": _first(r"Coverage Determination:\s*([A-Z]+)", text),
            "damages_description": _first(r"Description of Loss:\s*\n(.+)", text),
            "supporting_documents": ["photos", "contractor estimate"],
            "intent": "first_notice_of_loss",
            "subject_matter": "Property damage claim",
            "keywords": ["fnol", "property", "water"],
            "claim_checklist": [
                "Cause of Loss: water intrusion",
                "Estimate: contractor quote on file",
            ],
            "confidence": 0.98,
        }
    return {"confidence": 0.4}


def judge(extracted: dict[str, Any]) -> dict[str, Any]:
    conf = float(extracted.get("confidence") or 0)
    if conf >= 0.9:
        return {"verdict": "complete", "score": 0.96, "findings": []}
    if conf >= 0.7:
        return {"verdict": "partial", "score": 0.72, "findings": ["some fields thin"]}
    return {"verdict": "incomplete", "score": 0.4, "findings": ["extraction hollow"]}


def arbiter(judge_verdict: str) -> dict[str, Any]:
    if judge_verdict == "partial":
        return {
            "decision": "accept_with_caveats",
            "reasoning": "usable extraction with gaps",
            "fields_to_fix": [],
            "handoff_summary": None,
        }
    return {
        "decision": "human_review",
        "reasoning": "cannot resolve",
        "fields_to_fix": [],
        "handoff_summary": "Lane B exhausted — needs operator eyes",
    }


def boss(conflict: bool) -> dict[str, Any]:
    if conflict:
        return {"decision": "review", "reasoning": "matter conflict needs a human"}
    return {"decision": "approved", "reasoning": "that's what she said — approved"}
