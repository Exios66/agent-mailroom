<div align="center">

# 🚶 The Mailroom (Agent)

**The llm-mailroom document pipeline, on a walking office floor.**

A self-contained legal-document mailroom: one state machine per document, specialist agents at desks, a hash-chained audit log, and a pixel floor where envelopes fly from reception to the boss.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Pipeline](https://img.shields.io/badge/pipeline-llm--mailroom%20v0.6.0-blue)](https://github.com/Exios66/llm-mailroom)
[![Scoring](https://img.shields.io/badge/scoring-llm--dojo--scoring%20v0.12.1-purple)](https://github.com/Exios66/llm-dojo-scoring)

</div>

---

## What You Get

| Feature | Description |
|:---|:---|
| **Core pipeline** | intake → classify → extract → judge → report → archive. Happy path: **two LLM calls** |
| **Six live doc classes** | `contract`, `merger_agreement`, `corporate_record`, `correspondence`, `compliance_filing`, `insurance_claim` |
| **Pared extraction** | CUAD/MAUD/insurance checklists + semantic trio (`intent` / `subject_matter` / `keywords`) |
| **Inbox watcher** | txt / md / pdf / docx land in the inbox; the watcher claims each file once |
| **Hub datasets** | Pull [Lucius-Morningstar](https://huggingface.co/Lucius-Morningstar) rows onto the same inbox |
| **OpenRouter-first** | Primary provider is OpenRouter; add OpenAI, Ollama, vLLM, or generic. Missing keys → `mock` |
| **Hive mailboxes** | One JSON file per message, single-writer desks, speech acts |
| **Office floor** | LimeZu rooms, walking avatars, thought clouds, flying envelopes |
| **SQLite-first** | `data/mailroom.db` + filesystem bins. Local venv or Docker. |

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# optional: OPENROUTER_API_KEY=sk-or-...
python -m agent_mailroom
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). **Drop a pile** sends the HarborPoint fixtures across the floor. **Datasets** pulls Lucius-Morningstar Hub rows. **Topics** queues or launches a brief.

Without an OpenRouter key the floor uses the mock harness so you can still walk the pipeline.

<details>
<summary>Docker quick start</summary>

```bash
cp -n .env.example .env   # optional keys; mock works without them
docker compose up --build
```

Open [http://127.0.0.1:8000/office/](http://127.0.0.1:8000/office/). Compose binds the API on host port `${MAILROOM_PORT:-8000}`, persists SQLite + bins in `./data`.

```bash
curl -X POST http://127.0.0.1:8000/v1/upload \
  -F "file=@fixtures/samples/harborpoint_msa.txt" \
  -F "matter_id=MAILROOM"

curl -X POST http://127.0.0.1:8000/v1/datasets/pull \
  -H 'content-type: application/json' \
  -d '{"corpus":"docclass-pilot","limit":3,"matter_id":"HUB"}'
```

</details>

## The Floor

| Desk | Agent |
|:---|:---|
| Reception | Sorter / reviewer |
| Bay A | Contracts / corporate records |
| Bay B | Correspondence / compliance / claims |
| Judge chamber | Judge / arbiter |
| Boss office | Escalation + human review |
| Report / archive | Reporter / archivist |

Maroon and gold chrome, cream SNES panels, ink that is never pure black. Rooms are painted with [LimeZu Modern Interiors](https://limezu.itch.io/moderninteriors). Avatars, thought clouds, and envelopes stay original procedural pixels.

## Providers

<div align="center">

| Harness | Role |
|:---|:---|
| `openrouter` | **Primary.** Set `OPENROUTER_API_KEY`. Default model `qwen/qwen3.7-flash`. |
| `openai` | Official OpenAI or an `OPENAI_BASE_URL` compatible proxy |
| `ollama` | Local OpenAI-compatible server |
| `vllm` | Self-hosted or Modal vLLM |
| `generic` | Any other OpenAI-style `GENERIC_BASE_URL` |
| `mock` | Deterministic offline specialists (tests + no-key fallback) |

</div>

`MAILROOM_LLM_PROVIDER` selects the requested harness. `MAILROOM_LLM_FALLBACK` (default `mock`) is used when the key is missing. Pin per-desk models with `MAILROOM_AGENT_MODELS=sorter=qwen/qwen3.7-flash,judge=deepseek/deepseek-v4-flash`.

## API

Same producer shape as llm-mailroom. Prefer `/v1`.

<details>
<summary>Full endpoint list</summary>

| Method | Path | Role |
|:---|:---|:---|
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
| `GET` | `/v1/ops/status` | Watcher, inbox pending, stage counts |
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

</details>

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
tests/                routing, audit, e2e, watcher, intake, hub, tiles, CSP, API
docs/ARCHITECTURE.md  contracts and data flow
```

## License

MIT for original code. See [LICENSE](LICENSE). LimeZu tilesets are **not** MIT — see [office/tiles/LIMEZUASSETS-LICENSE.txt](office/tiles/LIMEZUASSETS-LICENSE.txt) and credit [LimeZu](https://limezu.itch.io/).

---

<div align="center">

**[llm-mailroom](https://github.com/Exios66/llm-mailroom)** ·
**[llm-entity-extraction](https://github.com/Exios66/llm-entity-extraction)** ·
**[llm-dojo-scoring](https://github.com/Exios66/llm-dojo-scoring)** ·
**[The-Mailroom](https://github.com/Exios66/The-Mailroom)**

<sub>Built by the governed evaluation family under <a href="https://github.com/Exios66">@Exios66</a> · 2026</sub>

</div>
