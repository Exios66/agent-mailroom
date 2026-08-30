from pathlib import Path

from agent_mailroom.pipeline.conflicts import detect_conflict
from agent_mailroom.pipeline.runner import run_document
from agent_mailroom.pipeline.state import RunState
from agent_mailroom.storage.catalog import get_document


OTHER_MSA = """MASTER SERVICES AGREEMENT

This Master Services Agreement dated January 1, 2026
by and between Scranton Paper Corporation and Client Services LLC.

NOW, THEREFORE, in consideration of the mutual covenants herein, the parties agree.

Governing Law. This Agreement is governed by the laws of the State of New York.

IN WITNESS WHEREOF the parties have executed this Agreement.
"""


def test_detect_conflict_empty_matter():
    state = RunState(
        doc_id="c2",
        matter_id="NONE",
        original_filename="b.txt",
        file_path=Path("b.txt"),
        doc_type="contract",
        extracted_data={"parties": ["Scranton Paper Corporation"]},
    )
    hit, reason = detect_conflict(state)
    assert hit is False
    assert reason is None


def test_same_matter_entity_mismatch_goes_to_review(tmp_path, samples):
    first = run_document(samples / "harborpoint_msa.txt", matter_id="CONFLICT")
    assert first.stage == "archived"
    other = tmp_path / "other_msa.txt"
    other.write_text(OTHER_MSA, encoding="utf-8")
    second = run_document(other, matter_id="CONFLICT")
    assert second.conflict_detected
    assert second.stage == "review"
    assert "conflict" in (second.escalation_reason or "").lower()
    row = get_document(second.doc_id)
    assert row["stage"] == "review"
    assert "conflict" in (row["escalation_reason"] or "").lower()
