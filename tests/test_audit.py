from agent_mailroom.storage.audit import compute_entry_hash, verify_chain, write_audit
from agent_mailroom.storage.db import init_db


def test_hash_chain_is_tamper_evident():
    init_db()
    write_audit(doc_id="d1", matter_id="M", event="ingested", actor="intake", filename="a.txt")
    write_audit(doc_id="d1", matter_id="M", event="classified", actor="sorter", detail={"doc_type": "contract"})
    valid, entries = verify_chain("d1")
    assert valid
    assert len(entries) == 2
    assert entries[0]["prev_hash"] == ""
    assert entries[1]["prev_hash"] == entries[0]["entry_hash"]

    expected = compute_entry_hash(
        prev_hash=entries[0]["prev_hash"],
        doc_id=entries[0]["doc_id"],
        entry_id=entries[0]["entry_id"],
        matter_id=entries[0]["matter_id"],
        actor=entries[0]["actor"],
        timestamp=entries[0]["timestamp"],
        event=entries[0]["event"],
        detail=entries[0]["detail"],
    )
    assert expected == entries[0]["entry_hash"]
