#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_mailroom.observability.field_scoring import score_extraction  # noqa: E402
from agent_mailroom.storage.catalog import list_documents  # noqa: E402
from agent_mailroom.storage.db import init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Score archived extractions against a golden JSON file")
    parser.add_argument("--golden", required=True, help="Path to golden expectations JSON")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    os.environ.setdefault("MAILROOM_BASE_DIR", str(ROOT / "data"))
    init_db()
    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    docs = [row for row in list_documents(args.limit) if row.get("stage") == "archived"]
    results = []
    for row in docs:
        expected = golden.get(row["doc_id"]) or golden.get(row["original_filename"])
        if not expected:
            continue
        # Score with the document's own class field map (every row used to be
        # scored as a contract, so claims/correspondence fields got the wrong
        # scorers). A golden entry may pin the class with "doc_type".
        doc_class = (expected.get("doc_type") if isinstance(expected, dict) else None) or row.get("doc_type")
        gold = {k: v for k, v in expected.items() if k != "doc_type"} if isinstance(expected, dict) else {}
        score = score_extraction(row.get("extracted_data"), gold, doc_id=row["doc_id"], doc_class=doc_class)
        results.append({"doc_id": row["doc_id"], "filename": row["original_filename"], "doc_type": doc_class, **score})
    aggregate = round(sum(r["aggregate"] for r in results) / len(results), 4) if results else 0.0
    by_class: dict[str, list[float]] = {}
    for r in results:
        by_class.setdefault(str(r.get("doc_type") or "unknown"), []).append(float(r["aggregate"]))
    per_class = {k: {"n": len(v), "aggregate": round(sum(v) / len(v), 4)} for k, v in sorted(by_class.items())}
    print(json.dumps({"evaluated": len(results), "aggregate": aggregate, "by_class": per_class, "documents": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
