from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

import os

import httpx

from agent_mailroom.pipeline.bins import enqueue_inbox
from agent_mailroom.pipeline.hf_corpora import adapt_hub_row, pipeline_corpora, resolve_corpus
from agent_mailroom.pipeline.watcher import scan_inbox

VIEWER = os.environ.get("HF_DATASETS_SERVER", "https://datasets-server.huggingface.co").rstrip("/") + "/rows"
MAX_PULL = 25

Fetcher = Callable[[str], dict[str, Any]]


def _default_fetch(url: str) -> dict[str, Any]:
    with httpx.Client(timeout=60.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def catalog() -> list[dict[str, Any]]:
    return pipeline_corpora()


def pull_corpus(
    name: str,
    *,
    limit: int = 5,
    offset: int = 0,
    config: str | None = None,
    split: str | None = None,
    matter_id: str = "HUB",
    fetcher: Fetcher | None = None,
) -> dict[str, Any]:
    corp = resolve_corpus(name)
    if not corp.get("pipeline"):
        raise ValueError(f"{corp['slug']} is not a pipeline ingest corpus")
    n = max(1, min(int(limit), MAX_PULL))
    off = max(0, int(offset))
    cfg = config or corp.get("gt_config") or corp.get("default_config") or "default"
    spl = split or corp.get("default_split") or "train"
    url = (
        f"{VIEWER}?dataset={corp['id']}&config={cfg}&split={spl}"
        f"&offset={off}&length={n}"
    )
    payload = (fetcher or _default_fetch)(url)
    rows = payload.get("rows") or []
    started: list[dict[str, Any]] = []
    for item in rows:
        raw = item.get("row") if isinstance(item, dict) and "row" in item else item
        adapted = adapt_hub_row(raw if isinstance(raw, dict) else {}, corp)
        text = str(adapted.get("doc_text") or "").strip()
        if not text:
            continue
        filename = str(adapted.get("filename") or "hub.txt")
        if not filename.lower().endswith((".txt", ".md")):
            filename = f"{filename}.txt"
        doc_id = str(uuid4())
        enqueue_inbox(
            text.encode("utf-8"),
            filename,
            doc_id=doc_id,
            matter_id=matter_id,
            source=str(corp.get("source_tag") or "huggingface"),
        )
        started.append(
            {
                "doc_id": doc_id,
                "filename": filename,
                "expected": adapted.get("expected"),
                "expected_subclass": adapted.get("expected_subclass"),
                "corpus": corp["slug"],
            }
        )
    scanned = scan_inbox() if started else []
    return {
        "corpus": corp,
        "config": cfg,
        "split": spl,
        "offset": off,
        "requested": n,
        "started": started,
        "scanned": scanned,
        "hub_rows": payload.get("num_rows_total"),
    }
