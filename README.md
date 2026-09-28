<div align="center">

# Agent Mailroom

**The llm-mailroom document pipeline, on a walking office floor.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Release](https://img.shields.io/badge/release-0.3.0-maroon)](CHANGELOG.md)
[![Pipeline](https://img.shields.io/badge/pipeline-llm--mailroom%200.7.1-blue)](https://github.com/Exios66/llm-mailroom)
[![Scoring](https://img.shields.io/badge/scoring-llm--dojo--scoring%20v0.16.0-purple)](https://github.com/Exios66/llm-dojo-scoring)
[![Dataset](https://img.shields.io/badge/dataset-mailroom--dataset%20v9.1-orange)](https://huggingface.co/datasets/Lucius-Morningstar/mailroom-dataset)
[![Contributor](https://img.shields.io/badge/contributor-Exios66-blue)](https://github.com/Exios66)

</div>

---

## What You Get

| Feature | Description |
| :--- | :--- |
| **Core pipeline** | intake → classify → extract → judge → report → archive. Happy path: **two LLM calls** |
| **Five live doc classes** | `contract`, `merger_agreement` (own MAUD specialist), `corporate_record`, `correspondence`, `insurance_claim` (+ the `unknown` routing token; `compliance_filing` is retired upstream) |
| **Pared extraction** | CUAD/MAUD/insurance checklists + semantic trio (`intent` / `subject_matter` / `keywords`) |
| **Inbox watcher** | txt / md / pdf / docx and images land in the inbox; the watcher claims each file once |
| **Hub datasets** | Pull [Lucius-Morningstar](https://huggingface.co/Lucius-Morningstar) rows (mailroom-dataset v9.1 pin) onto the same inbox |
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

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). **Demo pile** sends the HarborPoint fixtures across the floor. **Datasets** pulls Lucius-Morningstar Hub rows. **Brief** queues or launches a topic. Every document on the canvas is also listed under **On the floor** in the side panel, so the office works from the keyboard and with a screen reader.

Without an OpenRouter key the floor uses the mock harness so you can still walk the pipeline.

<details>
<summary>Docker quick start</summary>

```bash
cp -n .env.example .env   # optional keys; mock works without them
docker compose up --build
```

Open [http://127.0.0.1:8000/office/](http://127.0.0.1:8000/office/). Compose publishes the API on **host loopback** port `${MAILROOM_PORT:-8000}` and keeps SQLite + bins in the `mailroom-data` named volume (set `MAILROOM_DATA_DIR=./data` to bind a host directory, created and owned by uid 10001 first).

The container binds `0.0.0.0`, which counts as a public bind: without `MAILROOM_API_TOKEN` the API fails closed (503). Compose sets `MAILROOM_ALLOW_OPEN=1` only because it publishes on `127.0.0.1`. To expose the office on a network, set a token, `MAILROOM_ALLOW_OPEN=0`, and publish `8000:8000`.

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
| :--- | :--- |
| Reception | Sorter / reviewer |
| Bay A | Contracts / corporate records / merger agreements (Toby) |
| Bay B | Correspondence / claims |
| Judge chamber | Judge / arbiter |
| Boss office | Escalation + human review |
| Report / archive | Reporter / archivist |

Maroon and gold chrome, cream panels in light mode and plum panels in dark mode (follows the OS), ink that is never pure black. The canvas scales in whole tile multiples when it fits and fills the column otherwise. Rooms are painted with [LimeZu Modern Interiors](https://limezu.itch.io/moderninteriors). Avatars, thought clouds, and envelopes stay original procedural pixels.

## Providers

<div align="center">

| Harness | Role |
| :--- | :--- |
| `openrouter` | **Primary.** Set `OPENROUTER_API_KEY`. Default model `qwen/qwen3.7-flash`. |
| `openai` | Official OpenAI or an `OPENAI_BASE_URL` compatible proxy |
| `ollama` | Local OpenAI-compatible server |
| `vllm` | Self-hosted or Modal vLLM |
| `generic` | Any other OpenAI-style `GENERIC_BASE_URL` |
| `mock` | Deterministic offline specialists (tests + no-key fallback) |

</div>

`MAILROOM_LLM_PROVIDER` selects the requested harness and wins over the taxonomy. `MAILROOM_LLM_FALLBACK` (default `mock`) is used when the key is missing. Per-agent model, temperature, `max_tokens`, input budget and `reasoning_effort` come from `config/taxonomy.yaml` (mirrors llm-mailroom 0.7.1: every agent on `qwen/qwen3.7-flash`); local providers map the OpenRouter id through `vllm_model_map` / `ollama_model_map` / `llamafile_model_map`. Pin per-desk models with `MAILROOM_AGENT_MODELS=sorter=qwen/qwen3.7-flash,judge=deepseek/deepseek-v4-flash`. Transient failures retry with backoff per `llm_retry`; 4xx other than 408/429 do not retry.

## API

Same producer shape as llm-mailroom. Every route is under `/v1` (the 0.2.x bare aliases are gone, except a `/health` probe). With `MAILROOM_API_TOKEN` set, every route except `/v1/health`, `/v1/meta` and `/v1/auth/login` needs `Authorization: Bearer <token>`, and `/ws` needs `?token=`.

<details>
<summary>Full endpoint list</summary>

| Method | Path | Role |
| :--- | :--- | :--- |
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
| `POST` | `/v1/review/{doc_id}/resolve` | `decision` approved/rejected × `disposition` resume/record/requeue/complete (llm-mailroom contract) |
| `GET` | `/v1/ops/status` | Watcher, inbox pending, stage counts |
| `GET` | `/v1/queue` | Inbox hopper + in-flight |
| `GET` | `/v1/inspect/{id}` | Catalog + audit + source + conflict |
| `GET` | `/v1/archive` | Filed documents |
| `GET` | `/v1/archive/{id}/verify` | Hash-chain validity |
| `GET` | `/v1/matters` | Matter index |
| `GET` | `/v1/failed` | Rejected / failed returns |
| `GET` | `/v1/classified` | Post-sort snapshots |
| `GET` | `/v1/search` | Lookup by id, matter, filename, class |
| `POST` | `/v1/ops/recover` | Requeue stuck processing claims to the inbox |
| `POST` | `/v1/ops/sweep` | Boss tray walk |
| `GET` | `/v1/floor` | Office snapshot |
| `GET` | `/v1/hive` | Roster + inboxes |
| `GET` | `/v1/documents/{doc_id}/source` | Extracted source text (`?download=1` for bytes) |
| `POST` | `/v1/auth/login` | Operator JWT (fails closed on a public bind with defaults) |
| `WS` | `/ws` | Live pipeline + hive events |

</details>

## Tests

```bash
python -m pytest tests -q
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

## Monorepo & sync

This repo is also `packages/agent-mailroom` inside the
[Digital-Mailroom](https://github.com/LLM-Mailroom-Services/Digital-Mailroom)
monorepo. `scripts/sync_packages.py` (monorepo root) reconciles the two:
work landed here flows monorepo-ward with `pull --squash`; monorepo fixes
flow out with `push`. `status` shows drift. The monorepo re-adds its
`[tool.uv.sources]` workspace override for `llm-dojo-scoring`; the
standalone `pyproject.toml` keeps only the release git pin. Test tier
there: `uv run pytest packages/agent-mailroom/tests`. See
[CHANGELOG.md](CHANGELOG.md) and [AGENTS.md](AGENTS.md).

---

<div align="center">

**[llm-mailroom](https://github.com/Exios66/llm-mailroom)** ·
**[llm-entity-extraction](https://github.com/Exios66/llm-entity-extraction)** ·
**[llm-dojo-scoring](https://github.com/Exios66/llm-dojo-scoring)** ·
**[The-Mailroom](https://github.com/Exios66/The-Mailroom)**

<sub>Built by the governed evaluation family under <a href="https://github.com/Exios66">@Exios66</a> · 2026</sub>

</div>
