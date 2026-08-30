from agent_mailroom.pipeline.report import compile_matter_record
from agent_mailroom.pipeline.runner import run_document
from agent_mailroom.schemas.documents import ContractExtraction, EXTRACTION_SCHEMAS
from agent_mailroom.storage.audit import verify_chain
from agent_mailroom.storage.catalog import get_document


def test_contract_archives(samples):
    state = run_document(samples / "harborpoint_msa.txt", matter_id="MATTER-MSA")
    assert state.doc_type == "contract"
    assert state.stage == "archived"
    assert state.extracted_data
    assert "key_obligations" not in (state.extracted_data or {})
    assert "cuad_clauses" in (state.extracted_data or {})
    assert state.report and "Document type: contract" in state.report
    assert "judge_verify" not in state.routing_path  # happy path = classify + extract only
    row = get_document(state.doc_id)
    assert row["stage"] == "archived"
    assert row.get("report")
    valid, entries = verify_chain(state.doc_id)
    assert valid
    assert any(e["event"] == "archived" for e in entries)
    assert any(e["event"] == "report_compiled" for e in entries)


def test_claim_archives(samples):
    state = run_document(samples / "acme_claim.txt", matter_id="MATTER-CLM")
    assert state.doc_type == "insurance_claim"
    assert state.stage == "archived"
    assert state.extracted_data["claim_number"] == "2026-CLM-041702"
    assert "claim_checklist" in state.extracted_data
    assert "intent" in state.extracted_data


def test_ambiguous_goes_to_review(samples):
    state = run_document(samples / "ambiguous_memo.txt", matter_id="MATTER-MIX")
    assert state.stage == "review"
    assert "human_review" in state.routing_path or state.graph_node == "human_review"


def test_procedural_report_has_no_llm_marker():
    record = compile_matter_record(
        {
            "doc_type": "contract",
            "extracted_data": {"document_name": "MSA", "parties": ["A", "B"]},
            "classification_confidence": 0.99,
            "extraction_confidence": 0.98,
            "arbiter_decision": "accept_with_caveats",
            "arbiter_reasoning": "thin term_length",
        }
    )
    assert record["procedural"] is True
    assert "Document type: contract" in record["summary"]
    assert "Caveats:" in record["summary"]
    assert "thin term_length" in record["summary"]


def test_pared_contract_schema_rejects_legacy_fields():
    model = EXTRACTION_SCHEMAS["contract"]
    assert issubclass(model, ContractExtraction)
    fields = set(model.model_fields)
    assert "cuad_clauses" in fields
    assert "maud_clauses" in fields
    assert "key_obligations" not in fields
    assert "termination_clauses" not in fields
