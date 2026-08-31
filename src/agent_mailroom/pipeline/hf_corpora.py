"""Lucius-Morningstar Hugging Face corpora the mailroom can pull onto the floor.

Mirrors llm-mailroom ``pipeline/hf_corpora.py`` so the office and the pipeline
share the same Hub catalog, aliases, and row adapters.
"""

from __future__ import annotations

import json
from typing import Any

ORG = "Lucius-Morningstar"
FULL_CORPUS_ID = f"{ORG}/docclass-merged"
EXAMPLES_ID = f"{ORG}/docclass-pilot"

HUB_CLASSES: tuple[str, ...] = (
    "contract",
    "merger_agreement",
    "corporate_record",
    "correspondence",
    "insurance_claim",
)

CORPORA: dict[str, dict[str, Any]] = {
    "docclass-merged": {
        "slug": "docclass-merged",
        "id": FULL_CORPUS_ID,
        "role": "full_corpus",
        "pipeline": True,
        "n_docs": 1650,
        "classes": list(HUB_CLASSES),
        "gt_config": "ground_truth",
        "row_shape": "docclass",
        "text_field": "doc_text",
        "default_config": "default",
        "default_split": "train",
        "source_tag": "source-docclass-merged",
        "note": "CUAD + MAUD + S-1 + Enron sample + CMS claims (v7, issue #5 intent hydration).",
    },
    "docclass-pilot": {
        "slug": "docclass-pilot",
        "id": EXAMPLES_ID,
        "role": "class_subclass_examples",
        "pipeline": True,
        "n_docs": 138,
        "classes": list(HUB_CLASSES),
        "gt_config": "ground_truth",
        "row_shape": "docclass",
        "text_field": "doc_text",
        "default_config": "ground_truth",
        "default_split": "train",
        "source_tag": "source-docclass-pilot",
        "note": "Stratified slice of docclass-merged — safest pile for the floor.",
    },
    "enron-correspondence-dedup": {
        "slug": "enron-correspondence-dedup",
        "id": f"{ORG}/enron-correspondence-dedup",
        "role": "correspondence_full",
        "pipeline": True,
        "n_docs": 247523,
        "classes": ["correspondence"],
        "default_class": "correspondence",
        "gt_config": "ground_truth",
        "row_shape": "enron",
        "text_field": "text",
        "default_config": "default",
        "default_split": "train",
        "source_tag": "source-enron-correspondence",
        "note": "Large correspondence corpus — pull a few rows, never the whole set.",
    },
    "cms-desynpuf-insurance-claims": {
        "slug": "cms-desynpuf-insurance-claims",
        "id": f"{ORG}/cms-desynpuf-insurance-claims",
        "role": "insurance_claims",
        "pipeline": True,
        "n_docs": 400,
        "classes": ["insurance_claim"],
        "default_class": "insurance_claim",
        "gt_config": None,
        "row_shape": "cms_inline",
        "text_field": "doc_text",
        "default_config": "default",
        "default_split": "train",
        "source_tag": "source-cms-desynpuf",
        "note": "Synthetic CMS claims with inline gold.",
    },
    "mailroom-cuad-contracts-full": {
        "slug": "mailroom-cuad-contracts-full",
        "id": f"{ORG}/mailroom-cuad-contracts-full",
        "role": "cuad_contracts",
        "pipeline": True,
        "n_docs": 510,
        "classes": ["contract"],
        "default_class": "contract",
        "gt_config": None,
        "row_shape": "braintrust_mirror",
        "text_field": "input",
        "default_config": "default",
        "default_split": "train",
        "source_tag": "source-cuad-full",
    },
    "mailroom-cuad-contracts": {
        "slug": "mailroom-cuad-contracts",
        "id": f"{ORG}/mailroom-cuad-contracts",
        "role": "cuad_contracts_sample",
        "pipeline": True,
        "n_docs": 50,
        "classes": ["contract"],
        "default_class": "contract",
        "gt_config": None,
        "row_shape": "braintrust_mirror",
        "text_field": "input",
        "default_config": "default",
        "default_split": "train",
        "source_tag": "source-cuad-sample",
    },
    "legalbench-full": {
        "slug": "legalbench-full",
        "id": f"{ORG}/legalbench-full",
        "role": "legalbench_tasks",
        "pipeline": False,
        "n_docs": None,
        "classes": [],
        "gt_config": None,
        "row_shape": "legalbench_tasks",
        "text_field": None,
        "source_tag": "source-legalbench-full",
        "note": "LegalBench task pack — not a document-pipeline ingest corpus.",
    },
}

_ALIASES = {
    "v5": "docclass-merged",
    "v7": "docclass-merged",
    "full": "docclass-merged",
    "merged": "docclass-merged",
    "examples": "docclass-pilot",
    "pilot": "docclass-pilot",
    "enron": "enron-correspondence-dedup",
    "correspondence": "enron-correspondence-dedup",
    "claims": "cms-desynpuf-insurance-claims",
    "insurance": "cms-desynpuf-insurance-claims",
    "cuad": "mailroom-cuad-contracts-full",
    "cuad-full": "mailroom-cuad-contracts-full",
    "cuad-sample": "mailroom-cuad-contracts",
}


def pipeline_corpora() -> list[dict[str, Any]]:
    return [dict(row) for row in CORPORA.values() if row.get("pipeline")]


def resolve_corpus(name: str | None) -> dict[str, Any]:
    raw = (name or "docclass-pilot").strip()
    if raw.startswith(f"{ORG}/"):
        raw = raw.split("/", 1)[1]
    slug = _ALIASES.get(raw, raw)
    if slug not in CORPORA:
        known = ", ".join(sorted(CORPORA))
        raise KeyError(f"unknown Hugging Face corpus {name!r}; known: {known}")
    return dict(CORPORA[slug])


def adapt_hub_row(row: dict[str, Any], corpus: dict[str, Any] | None = None) -> dict[str, Any]:
    corp = corpus or resolve_corpus("docclass-pilot")
    shape = corp.get("row_shape") or "docclass"
    data = dict(row or {})
    if shape == "braintrust_mirror":
        text = ""
        raw_in = data.get("input") or data.get("doc_text") or ""
        if isinstance(raw_in, str) and raw_in.lstrip().startswith("{"):
            try:
                parsed = json.loads(raw_in)
                if isinstance(parsed, dict):
                    text = str(parsed.get("doc_text") or "")
            except json.JSONDecodeError:
                text = raw_in
        elif isinstance(raw_in, str):
            text = raw_in
        meta = data.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        family = (
            meta.get("expected_subclass")
            or meta.get("category")
            or (meta.get("applicable_categories") or [None])[0]
            or ""
        )
        if isinstance(family, list):
            family = family[0] if family else ""
        expected = data.get("expected")
        if str(expected or "") not in HUB_CLASSES:
            expected = corp.get("default_class") or "contract"
        return {
            "filename": str(data.get("filename") or data.get("id") or "cuad.txt"),
            "doc_text": text,
            "expected": expected,
            "expected_subclass": str(family or data.get("expected_subclass") or ""),
            "metadata": meta,
        }
    if shape == "enron":
        data.setdefault("doc_text", data.get("text") or "")
        if not data.get("expected"):
            data["expected"] = corp.get("default_class") or "correspondence"
        data.setdefault("filename", data.get("id") or "enron.txt")
        return data
    if shape == "cms_inline":
        data.setdefault("expected", "insurance_claim")
        data.setdefault("filename", data.get("filename") or "claim.txt")
        return data
    field = corp.get("text_field") or "doc_text"
    if field != "doc_text" and not data.get("doc_text"):
        data["doc_text"] = data.get(field) or ""
    if not data.get("expected") and corp.get("default_class"):
        data["expected"] = corp["default_class"]
    data.setdefault("filename", data.get("filename") or "document.txt")
    return data
