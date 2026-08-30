from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

API_BASE = os.environ.get("MAILROOM_API_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("MAILROOM_API_TOKEN", "").strip()


def fetch(path: str, timeout: float = 15.0) -> dict[str, Any] | None:
    headers = {"Accept": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(f"{API_BASE}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"GET {path} failed: {exc.code}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"GET {path} failed: {exc}", file=sys.stderr)
        return None


def render_floor(data: dict[str, Any]) -> str:
    lines = [f"FLOOR · {data.get('count', 0)} runs · provider {data.get('observability_provider', '?')}"]
    for run in (data.get("runs") or [])[:40]:
        lines.append(
            f"  {run.get('filename', run.get('doc_id')):<28} "
            f"{str(run.get('stage', '?')):<14} "
            f"{run.get('doc_type') or '—'}"
        )
    return "\n".join(lines)


def render_review(data: dict[str, Any]) -> str:
    docs = data.get("documents") or []
    lines = [f"REVIEW · {len(docs)} waiting"]
    for doc in docs[:40]:
        lines.append(f"  {doc.get('original_filename', doc.get('doc_id')):<28} {doc.get('escalation_reason') or ''}")
    return "\n".join(lines)


def render_metrics(data: dict[str, Any]) -> str:
    lines = [
        f"METRICS · {data.get('documents', 0)} documents",
        f"  observability: {json.dumps(data.get('observability') or {})}",
        f"  field_scoring: {json.dumps(data.get('field_scoring') or {})}",
    ]
    for stage, count in sorted((data.get("stages") or {}).items()):
        lines.append(f"  {stage}: {count}")
    return "\n".join(lines)


def render_history(data: dict[str, Any]) -> str:
    lines = [f"HISTORY · {data.get('count', 0)} runs · source {data.get('source')}"]
    for run in (data.get("runs") or [])[:40]:
        lines.append(
            f"  {run.get('filename', run.get('trace_id')):<28} "
            f"{str(run.get('stage', '?')):<14} "
            f"{run.get('updated_at') or run.get('created_at') or ''}"
        )
    return "\n".join(lines)


def render_inspect(doc_id: str, data: dict[str, Any]) -> str:
    run = data.get("run") or {}
    lines = [
        f"INSPECT · {doc_id}",
        f"  stage={run.get('stage')} type={run.get('doc_type')}",
        f"  routing={' → '.join(run.get('routing_path') or [])}",
    ]
    for span in (data.get("spans") or [])[:20]:
        lines.append(
            f"    [{span.get('seq')}] {span.get('name')} "
            f"{span.get('latency_ms', 0):.0f}ms"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent Mailroom TUI (scripting mode)")
    parser.add_argument("--once", action="store_true", help="Print one screen and exit")
    parser.add_argument(
        "--view",
        choices=["floor", "review", "metrics", "history", "inspect"],
        default="floor",
    )
    parser.add_argument("--trace", help="doc id for inspect view")
    args = parser.parse_args(argv)

    if args.view == "floor":
        data = fetch("/v1/floor")
        if not data:
            return 1
        print(render_floor(data))
    elif args.view == "review":
        data = fetch("/v1/review/queue")
        if not data:
            return 1
        print(render_review(data))
    elif args.view == "metrics":
        data = fetch("/v1/metrics")
        if not data:
            return 1
        print(render_metrics(data))
    elif args.view == "history":
        data = fetch("/v1/history")
        if not data:
            return 1
        print(render_history(data))
    elif args.view == "inspect":
        if not args.trace:
            print("--trace required for inspect view", file=sys.stderr)
            return 2
        data = fetch(f"/v1/runs/{args.trace}")
        if not data:
            return 1
        print(render_inspect(args.trace, data))

    if not args.once:
        print("(live TUI needs rich — use --once for scripting)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
