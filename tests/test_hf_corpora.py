import pytest

from agent_mailroom.pipeline.hf_corpora import adapt_hub_row, pipeline_corpora, resolve_corpus
from agent_mailroom.pipeline.hub import pull_corpus
from agent_mailroom.storage.catalog import get_document


def test_resolve_aliases():
    assert resolve_corpus("pilot")["id"] == "Lucius-Morningstar/docclass-pilot"
    assert resolve_corpus("Lucius-Morningstar/mailroom-corpus")["slug"] == "docclass-merged"
    assert resolve_corpus("claims")["default_class"] == "insurance_claim"
    with pytest.raises(KeyError):
        resolve_corpus("not-a-corpus")


def test_pipeline_catalog_skips_legalbench():
    slugs = {row["slug"] for row in pipeline_corpora()}
    assert "docclass-pilot" in slugs
    assert "legalbench-full" not in slugs


def test_adapt_cms_and_enron():
    cms = adapt_hub_row(
        {"doc_text": "COVERAGE DETERMINATION: APPROVED", "filename": "c.txt"},
        resolve_corpus("claims"),
    )
    assert cms["expected"] == "insurance_claim"
    enron = adapt_hub_row({"text": "Dear counsel,", "id": "e1"}, resolve_corpus("enron"))
    assert enron["expected"] == "correspondence"
    assert "Dear counsel" in enron["doc_text"]


def test_adapt_braintrust_mirror():
    row = adapt_hub_row(
        {
            "id": "cuad-1",
            "input": '{"doc_text":"MASTER SERVICES AGREEMENT\\nNOW, THEREFORE"}',
            "expected": "contract",
            "metadata": {"category": "msa"},
        },
        resolve_corpus("cuad-sample"),
    )
    assert "MASTER SERVICES" in row["doc_text"]
    assert row["expected"] == "contract"


def test_legalbench_is_not_ingestable():
    with pytest.raises(ValueError):
        pull_corpus("legalbench-full")


def test_pull_enqueues_and_runs(samples):
    text = (samples / "harborpoint_msa.txt").read_text(encoding="utf-8")

    def fake(_url: str) -> dict:
        return {
            "rows": [{"row": {"doc_text": text, "filename": "hub_msa.txt", "expected": "contract"}}],
            "num_rows_total": 1,
        }

    result = pull_corpus("docclass-pilot", limit=1, matter_id="HUB", fetcher=fake)
    assert len(result["started"]) == 1
    row = get_document(result["started"][0]["doc_id"])
    assert row["stage"] == "archived"
    assert row["matter_id"] == "HUB"
