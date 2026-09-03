# Architecture

The Mailroom is a self-contained hybrid:

- **Pipeline** — the llm-mailroom document state machine (classify → extract → [judge/arbiter on Lane B] → procedural matter-record → archive), including filesystem bins, a SQLite catalog, and a SHA-256 hash-chained audit log.
- **Hive** — atomic mailboxes. Agents write JSON to `outbox/`; the router delivers to `inbox/` and the office draws a flying envelope.
- **Office** — a walking pixel floor branded **The Mailroom**. LimeZu Modern Interiors tilesets paint the rooms when `office/tiles/` is present; the original procedural rooms are the fallback. A hardened Electron shell can wrap the same `/office/` UI the browser already uses.
- **Harnesses** — OpenRouter is primary. OpenAI, Ollama, vLLM, generic OpenAI-compatible, and mock are registered fallbacks.
- **Scoring** — deterministic field scoring via [llm-dojo-scoring](https://github.com/Exios66/llm-dojo-scoring) **v0.12.1** (same pin as llm-mailroom v0.6.0); `observability/field_scoring.py` is a shim + SQLite glue.
- **Hub corpora** — Lucius-Morningstar datasets pull through the same inbox the watcher already drains.

Uploads, demo piles, and filing-like topics **only write the inbox** (plus a `.meta` sidecar). The embedded watcher claims each file into `processing/` and runs the graph once. `MAILROOM_SYNC=1` drains the inbox in-request so tests stay deterministic. Do not call the runner on a file that is still sitting in the inbox — that double-runs.

```
upload / demo / topic ingest / drop
    │
    ▼
inbox bin + sidecar ──► watcher claim ──► intake ──► sorter (Pam)
                 │
                 ├── high confidence ──► specialist desk (Dwight / Angela / Jim / Toby / Meredith)
                 ├── medium band ──► Kelly second opinion ──► extract or review
                 └── unknown / exhausted ──► Michael's office (human review)
                                │
                                ▼
                         [Lane B judge/arbiter only when extraction is ambiguous]
                                │
                                ▼
                         procedural matter-record (Ryan desk, no LLM) ──► Creed's archive
```

Happy-path archive is **classify + extract only** (two LLM generations), matching [llm-mailroom v0.6.0](https://github.com/Exios66/llm-mailroom/releases/tag/v0.6.0). `compile_report` assembles a deterministic matter record; the reporter LLM is retired.
Routing thresholds live in [`src/agent_mailroom/config/taxonomy.yaml`](../src/agent_mailroom/config/taxonomy.yaml). They are not hardcoded.

The office is static files under `office/` served by the same FastAPI process. Live updates go over `/ws`. The display contract (`stage`, `doc_type`, review dispositions) matches The-Mailroom / llm-mailroom so this repo can sit at the center of that constellation.

**Mailroom desks.** The walking floor is no longer just a cartoon. Operators get the trays the pipeline already had:

- **Inbox hopper** — `GET /v1/queue` lists files still sitting in `inbox/` (catalog row is written at enqueue, before the watcher claims).
- **Review siding** — Approve / Record / Complete / Reject / Requeue, subclass, source text, extracted JSON. `GET /v1/inspect/{id}` merges catalog + audit chain + source + conflict detail.
- **Archive** — Creed’s shelf: list, inspect, hash-chain verify.
- **Matters** — group filings by `matter_id` (the `matters` table is touched on every persist).
- **Classified tray** — after sort, a snapshot lands in `classified/{doc_type}/` while the live file stays in processing.
- **Ops** — `POST /v1/ops/recover` requeues stale processing claims to the inbox (idempotent); `POST /v1/ops/sweep` has the boss ping the hive about review/failed/reconsider. `MAILROOM_JUDGE_VERIFY=off` skips the judge band. Reconsideration flags archived filings that are hollow, conflicted, or low-confidence.
- **Floor trays** — inbox hopper, classified cart, review siding, archive shelves, and the returns dump are clickable crates on the LimeZu (or procedural) floor. Parked filings stack there; in-flight work still walks to a desk. `GET /v1/floor` includes `bins` counts. Lookup (`GET /v1/search`) finds a filing by id, matter, filename, or class.
- **Returns** — rejected or failed filings list at `GET /v1/failed`. Classified snapshots list at `GET /v1/classified`.

**LimeZu floor.** `office/js/tiled.js` loads `office/tiles/manifest.json` + `maps/office.tmj` and blits the three LimeZu atlases onto the canvas. Spawn points from the Tiled map become pipeline desks (CEO → boss, organizer → sorter, PCs → specialists, architect/UX → judge/arbiter). Collision tiles drive walking. If a PNG or the manifest is missing, `office/js/layout.js` keeps the procedural 40×24 rooms so browser tests still have a floor.

**Electron.** `electron/main.js` loads `http://127.0.0.1:<port>/office/` only. Renderer: no Node, sandboxed, context-isolated. Preload IPC is `version` + LimeZu credits. The FastAPI process sends the same CSP (`script-src 'self'`, no `unsafe-eval`) on `/office` so Playwright and Electron exercise one UI.

**Live topics.** Operators can **queue** or **launch** briefs while the floor is running.

- `POST /v1/topics` with `action=queue` parks a row (`status=queued`). No hive mail yet.
- `POST /v1/topics` with `action=launch`, or `POST /v1/topics/{id}/launch`, delivers a hive `request` to the chosen desk (default: the boss), appends `hive/board.md`, and — if the body looks like a filing — drops it into the inbox so the pipeline runs it.
- `POST /v1/topics/{id}/complete` marks the brief done.

The Topics tab is the command-center composer for both paths.

**Hub pull.** `POST /v1/datasets/pull` reads the Hugging Face Dataset Viewer (`datasets-server.huggingface.co/rows`), adapts each row with the same `adapt_hub_row` shapes as llm-mailroom (`docclass`, `enron`, `cms_inline`, `braintrust_mirror`), writes inbox + sidecar, and lets the watcher claim the file. Default corpus is `docclass-pilot`. LegalBench is catalogued but not ingestable.

**LLM hard aborts** (timeouts, 401/403, 429, I/O, budget) land in the failed bin with a tagged `failure_class`. Soft quality misses still park on human review. JSON replies are parsed through a fence-tolerant decoder.

**Review Complete** rejects cross-class specialist fields and falls back to the parked manifest when the operator body is empty. `GET /documents/{doc_id}/source?download=1` streams original bytes. API tokens rotate via `MAILROOM_API_TOKENS` / `MAILROOM_API_TOKEN_REVOKED`. Ops recover requeues stale processing claims to the inbox idempotently (`--stale` on name collision).
