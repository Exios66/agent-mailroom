# Architecture

The Mailroom is a self-contained hybrid:

- **Pipeline** — the llm-mailroom document state machine (classify → extract → [judge/arbiter on Lane B] → procedural matter-record → archive), including filesystem bins, a SQLite catalog, and a SHA-256 hash-chained audit log.
- **Hive** — atomic mailboxes. Agents write JSON to `outbox/`; the router delivers to `inbox/` and the office draws a flying envelope.
- **Office** — a walking pixel floor branded **The Mailroom**. LimeZu Modern Interiors tilesets paint the rooms when `office/tiles/` is present; the original procedural rooms are the fallback. A hardened Electron shell can wrap the same `/office/` UI the browser already uses.
- **Harnesses** — OpenRouter is primary. OpenAI, Ollama, vLLM, generic OpenAI-compatible, and mock are registered fallbacks.
- **Scoring** — deterministic field scoring via [llm-dojo-scoring](https://github.com/Exios66/llm-dojo-scoring) **v0.16.0** (same pin as llm-mailroom 0.7.1 @959bb0b); `observability/field_scoring.py` is a shim + SQLite glue.
- **Upstream mirror** — `config/taxonomy.yaml` and `agents/prompts.json` mirror llm-mailroom 0.7.1 @959bb0b: five live classes (merger_agreement has its own `merger_agreement_specialist` + `MergerAgreementExtraction`; `compliance_filing` is retired), the per-agent harness keys, `llm_retry`, `run_limits`, `cost_models` and the local model maps.
- **Hub corpora** — Lucius-Morningstar datasets pull through the same inbox the watcher already drains.

Uploads, demo piles, and filing-like topics **only write the inbox** (plus a `.meta` sidecar). The embedded watcher claims each file into `processing/` and runs the graph once. `MAILROOM_SYNC=1` drains the inbox in-request so tests stay deterministic. Do not call the runner on a file that is still sitting in the inbox — that double-runs.

```
upload / demo / topic ingest / drop
    │
    ▼
inbox bin + sidecar ──► watcher claim ──► intake ──► sorter (Pam)
                 │
                 ├── high confidence ──► specialist desk (Dwight contracts / Toby mergers / Angela / Jim / Meredith)
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

**Hub pull.** `POST /v1/datasets/pull` reads the Hugging Face Dataset Viewer (`datasets-server.huggingface.co/rows`), adapts each row with the same `adapt_hub_row` shapes as llm-mailroom (`docclass`, `enron`, `cms_inline`, `braintrust_mirror`), writes inbox + sidecar, and lets the watcher claim the file. It only enqueues: the watcher claims the rows, so the request no longer blocks on every LLM call in the pile (`MAILROOM_SYNC=1` keeps the inline drain for tests). The office defaults to `docclass-pilot`; `resolve_corpus()` defaults to `docclass-merged` (mailroom-dataset v9.1, 2,979 train / 323 test, aliases `v8`/`v9`/`v9.1`/`mailroom-dataset`). LegalBench is catalogued but not ingestable.

**Tracing.** Each run is one `document-pipeline` CHAIN with verb-first child observations (`intake-document`, `classify-document`, `extract-fields`, `judge-verify`, `arbitrate-verdict`, `adjudicate-conflict`, `route-for-review`, `compile-report`, `write-catalog`, `archive-document`) typed per llm-mailroom's `NODE_OBSERVATION_TYPES`. Local spans are written in `finally`, so a failing node still shows up with its error. Langfuse context managers never swallow pipeline exceptions.

**LLM hard aborts** (timeouts, 401/403, 429, I/O, budget) propagate out of `run_agent` and land in the failed bin with a tagged `failure_class` (the 0.2.x nodes caught them and stored the error dict as the extraction). Soft quality misses still park on human review. The judge gate fails closed: a missing or unparseable verdict routes to human review, never straight to the report. A run that exceeds the 40-step safety cap parks on review instead of staying in `processing`. JSON replies are parsed through a fence-tolerant decoder.

**Security.** Bins take a slugged `matter_id` and a taxonomy `doc_type` (anything else is `unknown`), and resolved paths must stay inside their bin root. A non-loopback `MAILROOM_HOST` without an API token fails closed (503) unless `MAILROOM_ALLOW_OPEN=1`; operator login on a public bind refuses the default JWT secret and the seeded password. `/ws` checks the token and the browser Origin.

**Review resolve** follows the llm-mailroom contract: `decision` ∈ approved/rejected, `disposition` ∈ resume/record/requeue/complete. `record` is a paper trail on any stage (notes and a validated class override merge into the stored row). `requeue` sends the source back to the inbox as a fresh run and closes a parked row as superseded. Reject, resume and complete need a parked review file; complete requires `approved`, rejects cross-class specialist fields, and falls back to the parked manifest when the operator body is empty. Resume moves the parked copy back to processing and reports failures on the event stream and the audit log. `GET /v1/documents/{doc_id}/source?download=1` streams original bytes. API tokens rotate via `MAILROOM_API_TOKENS` / `MAILROOM_API_TOKEN_REVOKED`. Ops recover requeues stale processing claims (compared as real timestamps) to the inbox idempotently, with the original `doc_id` / `matter_id` sidecar (`--stale` on name collision).
