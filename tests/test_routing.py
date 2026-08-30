from pathlib import Path

from agent_mailroom.pipeline.routing import after_classify, after_extract, after_judge
from agent_mailroom.pipeline.state import RunState


def _state(**kwargs) -> RunState:
    base = RunState(doc_id="x", matter_id="M", original_filename="f.txt", file_path=Path("f.txt"))
    for key, value in kwargs.items():
        setattr(base, key, value)
    return base


def test_high_confidence_classify_goes_to_extract():
    nxt = after_classify(_state(doc_type="contract", classification_confidence=0.97, classification_attempts=1))
    assert nxt == "extract"


def test_medium_band_retries_then_lane_a():
    first = after_classify(_state(doc_type="correspondence", classification_confidence=0.82, classification_attempts=1))
    assert first == "retry_classify"
    second = after_classify(
        _state(doc_type="correspondence", classification_confidence=0.82, classification_attempts=2),
        retry=True,
    )
    assert second == "review_classify"


def test_unknown_goes_to_review():
    nxt = after_classify(_state(doc_type="unknown", classification_confidence=0.4, classification_attempts=1))
    assert nxt == "human_review"


def test_extract_judge_band():
    nxt = after_extract(_state(extraction_confidence=0.78, extraction_attempts=1))
    assert nxt == "judge_verify"


def test_extract_high_skips_judge():
    nxt = after_extract(_state(extraction_confidence=0.92, extraction_attempts=1))
    assert nxt == "compile_report"


def test_judge_partial_to_arbiter():
    nxt = after_judge(_state(judge_verdict="partial"))
    assert nxt == "arbiter"
