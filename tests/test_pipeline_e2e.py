from agent_mailroom.pipeline.runner import run_document
from agent_mailroom.storage.audit import verify_chain
from agent_mailroom.storage.catalog import get_document


def test_contract_archives(samples):
    state = run_document(samples / "harborpoint_msa.txt", matter_id="MATTER-MSA")
    assert state.doc_type == "contract"
    assert state.stage == "archived"
    assert state.extracted_data
    row = get_document(state.doc_id)
    assert row["stage"] == "archived"
    valid, entries = verify_chain(state.doc_id)
    assert valid
    assert any(e["event"] == "archived" for e in entries)


def test_claim_archives(samples):
    state = run_document(samples / "acme_claim.txt", matter_id="MATTER-CLM")
    assert state.doc_type == "insurance_claim"
    assert state.stage == "archived"
    assert state.extracted_data["claim_number"] == "2026-CLM-041702"


def test_ambiguous_goes_to_review(samples):
    state = run_document(samples / "ambiguous_memo.txt", matter_id="MATTER-MIX")
    assert state.stage == "review"
    assert "human_review" in state.routing_path or state.graph_node == "human_review"
