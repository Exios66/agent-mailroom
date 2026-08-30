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
        score = score_extraction(row.get("extracted_data"), expected, doc_id=row["doc_id"])
        results.append({"doc_id": row["doc_id"], "filename": row["original_filename"], **score})
    aggregate = round(sum(r["aggregate"] for r in results) / len(results), 4) if results else 0.0
    print(json.dumps({"evaluated": len(results), "aggregate": aggregate, "documents": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
