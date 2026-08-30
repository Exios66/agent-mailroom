from pathlib import Path

from agent_mailroom.config.loader import confidence
from agent_mailroom.pipeline.routing import after_arbiter, after_classify, after_extract, after_judge
from agent_mailroom.pipeline.state import RunState


def _state(**kwargs) -> RunState:
    base = RunState(doc_id="x", matter_id="M", original_filename="f.txt", file_path=Path("f.txt"))
    for key, value in kwargs.items():
        setattr(base, key, value)
    return base


def test_severity_gates_match_v060():
    global_cfg = confidence()
    assert global_cfg["retry_max"] == 2
    assert global_cfg["arbiter_retry_max"] == 2
    assert global_cfg["judge_max_passes"] == 3
    contract = confidence("contract")
    assert contract["high"] == 0.98
    assert contract["judge_band_high"] == 0.97
    correspondence = confidence("correspondence")
    assert correspondence["high"] == 0.95
    assert correspondence["low"] == 0.85


def test_high_confidence_classify_goes_to_extract():
    nxt = after_classify(_state(doc_type="contract", classification_confidence=0.99, classification_attempts=1))
    assert nxt == "extract"


def test_medium_band_retries_then_lane_a():
    # correspondence medium band: [0.85, 0.95)
    first = after_classify(_state(doc_type="correspondence", classification_confidence=0.88, classification_attempts=1))
    assert first == "retry_classify"
    second = after_classify(
        _state(doc_type="correspondence", classification_confidence=0.88, classification_attempts=2),
        retry=True,
    )
    assert second == "review_classify"


def test_unknown_goes_to_review():
    nxt = after_classify(_state(doc_type="unknown", classification_confidence=0.4, classification_attempts=1))
    assert nxt == "human_review"


def test_extract_judge_band():
    # contract Lane B: [0.90, 0.97)
    nxt = after_extract(
        _state(doc_type="contract", extraction_confidence=0.93, extraction_attempts=1)
    )
    assert nxt == "judge_verify"


def test_extract_high_skips_judge():
    nxt = after_extract(
        _state(doc_type="contract", extraction_confidence=0.98, extraction_attempts=1)
    )
    assert nxt == "compile_report"


def test_conflict_goes_to_boss():
    nxt = after_extract(
        _state(doc_type="contract", conflict_detected=True, extraction_confidence=0.98, extraction_attempts=1)
    )
    assert nxt == "boss_escalation"


def test_judge_partial_to_arbiter():
    nxt = after_judge(_state(judge_verdict="partial", judge_pass_count=1))
    assert nxt == "arbiter"


def test_arbiter_retry_bound_is_two():
    first = after_arbiter(_state(arbiter_decision="retry_extraction", arbiter_retry_count=1))
    assert first == "retry_extract"
    second = after_arbiter(_state(arbiter_decision="retry_extraction", arbiter_retry_count=2))
    assert second == "retry_extract"
    spent = after_arbiter(_state(arbiter_decision="retry_extraction", arbiter_retry_count=3))
    assert spent == "human_review"
