# The Mailroom

**The llm-mailroom document pipeline, on a walking office floor.**

A self-contained legal-document mailroom: one state machine per document, specialist agents at desks, a hash-chained audit log, and a pixel floor where envelopes fly from reception to the boss.

You talk to the floor. The boss desk only bothers you when a filing actually needs a human.

Pipeline contract from [llm-mailroom](https://github.com/Exios66/llm-mailroom) **v0.6.0** (happy-path classify + extract, procedural matter-record, severity-aware gates). Floor / hive language from [munder-difflin](https://github.com/chaitanyagiri/munder-difflin) and [The-Mailroom](https://github.com/Exios66/The-Mailroom). Corpora from [Lucius-Morningstar](https://huggingface.co/Lucius-Morningstar) on Hugging Face. This repo does not require those siblings at runtime.

## What you get

- **Core mailroom pipeline** — ingest → classify → (Lane A reviewer) → extract → (Lane B judge / arbiter on ambiguous extractions only) → procedural matter-record → catalog → archive. Happy path is **two LLM calls**.
- **Six live document classes** — `contract`, `merger_agreement`, `corporate_record`, `correspondence`, `compliance_filing`, `insurance_claim` (`unknown` parks on review)
- **Pared extraction** — CUAD/MAUD/insurance checklists + semantic trio (`intent` / `subject_matter` / `keywords`); no open `key_obligations` / `termination_clauses` / `key_provisions`
- **Inbox watcher** — txt / md / pdf / docx land in the inbox; the watcher claims each file once. Matter conflicts escalate to the boss.
- **Hub datasets** — pull [Lucius-Morningstar](https://huggingface.co/Lucius-Morningstar) rows (`docclass-pilot`, `docclass-merged`, Enron, CMS claims, CUAD) onto the same inbox
- **OpenRouter-first harness** — primary provider is OpenRouter; add OpenAI, Ollama, vLLM, or a generic OpenAI-compatible endpoint. Missing keys fall back to `mock`.
- **Hive mailboxes** — one JSON file per message, single-writer desks, speech acts (`request`, `inform`, `query`, …)
- **Office floor** — LimeZu rooms, walking avatars, thought clouds, flying envelopes
- **Mailroom desks** — inbox hopper, full review siding (record/complete/source), archive + audit verify, returns, matters, inspect (hash chain + source), lookup, ops recover/sweep
- **Floor trays** — clickable inbox / sorted / review / archive / returns crates on the walking floor, with stamp-colored piles
- **Desktop shell** — optional hardened Electron window around the same `/office/` UI the browser uses
- **SQLite-first** — `data/mailroom.db` + filesystem bins. Local venv or Docker.
- **Docker** — `Dockerfile` + Compose for the same `/office/` UI and `/v1` API

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# optional: OPENROUTER_API_KEY=sk-or-...
python -m agent_mailroom
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). **Drop a pile** sends the HarborPoint fixtures across the floor. **Datasets** pulls Lucius-Morningstar Hub rows. **Topics** queues or launches a brief.

Without an OpenRouter key the floor uses the mock harness so you can still walk the pipeline.

### Docker

```bash
cp -n .env.example .env   # optional keys; mock works without them
docker compose up --build
```

Open [http://127.0.0.1:8000/office/](http://127.0.0.1:8000/office/). Compose binds the API on host port `${MAILROOM_PORT:-8000}`, persists SQLite + bins in `./data`, and forces `MAILROOM_HOST=0.0.0.0` inside the container. To reach Ollama on the host, set `OLLAMA_BASE_URL=http://host.docker.internal:11434/v1` in `.env`.

```bash
curl -X POST http://127.0.0.1:8000/v1/upload \
  -F "file=@fixtures/samples/harborpoint_msa.txt" \
  -F "matter_id=MAILROOM"

curl -X POST http://127.0.0.1:8000/v1/datasets/pull \
  -H 'content-type: application/json' \
  -d '{"corpus":"docclass-pilot","limit":3,"matter_id":"HUB"}'
```

## Providers

| Harness | Role |
| --- | --- |
| `openrouter` | **Primary.** Set `OPENROUTER_API_KEY`. Default model `qwen/qwen3.7-flash`. |
| `openai` | Official OpenAI or an `OPENAI_BASE_URL` compatible proxy |
| `ollama` | Local OpenAI-compatible server |
| `vllm` | Self-hosted or Modal vLLM |
| `generic` | Any other OpenAI-style `GENERIC_BASE_URL` |
| `mock` | Deterministic offline specialists (tests + no-key fallback) |

`MAILROOM_LLM_PROVIDER` selects the requested harness. `MAILROOM_LLM_FALLBACK` (default `mock`) is used when the key is missing. Pin per-desk models with `MAILROOM_AGENT_MODELS=sorter=qwen/qwen3.7-flash,judge=deepseek/deepseek-v4-flash`.

## The floor

| Desk | Agent |
| --- | --- |
| Reception | Sorter / reviewer |
| Bay A | Contracts / corporate records |
| Bay B | Correspondence / compliance / claims |
| Judge chamber | Judge / arbiter |
| Boss office | Escalation + human review |
| Report / archive | Reporter / archivist |

Maroon and gold chrome, cream SNES panels, ink that is never pure black. Rooms are painted with [LimeZu Modern Interiors](https://limezu.itch.io/moderninteriors) (Complete Version — credit required). Avatars, thought clouds, and envelopes stay original procedural pixels. If the atlases are missing the floor falls back to the older 16px rooms.

## Desktop

The office is a static SPA. Electron is an optional shell, not a second UI:

```bash
cd electron && npm install
# with the API already running
MAILROOM_URL=http://127.0.0.1:8000 npm run start:attached
# or spawn both
python -m agent_mailroom --desktop
```

The window loads loopback `/office/` only: `contextIsolation`, `sandbox`, no Node in the renderer. Playwright and a normal browser hit the same URL. Office pages send `Content-Security-Policy: script-src 'self'` (no `unsafe-eval`).

## API

Same producer shape as llm-mailroom. Prefer `/v1`.

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/v1/health` | Liveness + watcher + harness |
| `GET` | `/v1/providers` | Requested / active harness and catalog |
| `GET` | `/v1/datasets` | Lucius-Morningstar corpus registry |
| `POST` | `/v1/datasets/pull` | Fetch Hub rows onto the inbox |
| `POST` | `/v1/upload` | Queue a document (202) |
| `POST` | `/v1/topics` | `action=queue` parks a brief; `action=launch` delivers it |
| `POST` | `/v1/topics/{id}/launch` | Dispatch a queued topic |
| `POST` | `/v1/topics/{id}/complete` | Mark a live topic done |
| `GET` | `/v1/topics` | Queue + live + done briefs |
| `POST` | `/v1/demo` | Drop fixture samples on the floor |
| `GET` | `/v1/status/{doc_id}` | Catalog row |
| `GET` | `/v1/audit/{doc_id}` | Hash-chained trail + validity |
| `GET` | `/v1/review/queue` | Human siding |
| `POST` | `/v1/review/{doc_id}/resolve` | `resume` / `record` / `requeue` / `complete` |
| `GET` | `/v1/ops/status` | Watcher, inbox pending, stage counts, review queue |
| `GET` | `/v1/queue` | Inbox hopper + in-flight |
| `GET` | `/v1/inspect/{id}` | Catalog + audit + source + conflict |
| `GET` | `/v1/archive` | Filed documents |
| `GET` | `/v1/archive/{id}/verify` | Hash-chain validity |
| `GET` | `/v1/matters` | Matter index |
| `GET` | `/v1/failed` | Rejected / failed returns |
| `GET` | `/v1/classified` | Post-sort snapshots |
| `GET` | `/v1/search` | Lookup by id, matter, filename, class |
| `POST` | `/v1/ops/recover` | Park stuck processing |
| `POST` | `/v1/ops/sweep` | Boss tray walk |
| `GET` | `/v1/floor` | Office snapshot |
| `GET` | `/v1/hive` | Roster + inboxes |
| `WS` | `/ws` | Live pipeline + hive events |

## Tests

```bash
pytest -q
```

Tests never call a hosted LLM. The mock sorter/specialists are deterministic over `fixtures/samples/`. Hub pulls are tested with a fake Dataset Viewer.

## Layout

```
src/agent_mailroom/   pipeline, agents, hive, storage, API, LLM harnesses
office/               pixel floor + mailroom desks (vanilla JS, no build step)
office/tiles/         LimeZu atlases, Tiled map, licence + attribution
electron/             hardened desktop shell (optional)
fixtures/samples/     HarborPoint demo pile
tests/                routing, audit, e2e, watcher, ingest, hub, tiles, CSP, API
docs/ARCHITECTURE.md  contracts and data flow
```

## License

MIT for original code. See [LICENSE](LICENSE). LimeZu tilesets are **not** MIT — see [office/tiles/LIMEZUASSETS-LICENSE.txt](office/tiles/LIMEZUASSETS-LICENSE.txt) and credit [LimeZu](https://limezu.itch.io/).
