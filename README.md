# Agent Mailroom

**The llm-mailroom pipeline, seated in a Dunder Mifflin office.**

A self-contained legal-document mailroom: one state machine per document, specialist agents at desks, a hash-chained audit log, and a pixel office floor where envelopes fly from reception to the boss.

You talk to the floor. Michael (the boss desk) only bothers you when a filing actually needs a human.

Inspired by [munder-difflin](https://github.com/chaitanyagiri/munder-difflin) (office + hive), [llm-mailroom](https://github.com/Exios66/llm-mailroom) (pipeline contract), and [The-Mailroom](https://github.com/Exios66/The-Mailroom) (floor / review / inspector). This repo does not require those siblings at runtime.

## What you get

- **Core mailroom pipeline** — ingest → classify → (Lane A reviewer) → extract → (Lane B judge / arbiter) → boss → human review → report → catalog → archive
- **Six live document classes** — `contract`, `merger_agreement`, `corporate_record`, `correspondence`, `compliance_filing`, `insurance_claim` (`unknown` parks on review)
- **Hive mailboxes** — one JSON file per message, single-writer desks, speech acts (`request`, `inform`, `query`, …)
- **Office floor** — original 16px rooms, procedural avatars, flying envelopes, review siding, hive + metrics + console
- **SQLite-first** — `data/mailroom.db` + filesystem bins. No Docker required.
- **Mock LLM by default** — `MAILROOM_LLM_PROVIDER=mock` runs the whole floor without keys. Flip to OpenRouter / Ollama / OpenAI when you want real models.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m agent_mailroom
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Click **Drop a pile** to send the HarborPoint fixtures across the floor. Use **Topics** (or **Brief floor**) to give the office work: **Queue** parks a brief; **Launch now** delivers an envelope to Michael (or another desk). Filing-like briefs also enter the pipeline.

```bash
# or enqueue one file
curl -X POST http://127.0.0.1:8000/v1/upload \
  -F "file=@fixtures/samples/harborpoint_msa.txt" \
  -F "matter_id=SCRANTON"
```

## The floor

| Desk | Agent | Cast |
|---|---|---|
| Reception | Sorter / reviewer | Pam / Kelly |
| Bay A | Contracts / corporate records | Dwight / Angela |
| Bay B | Correspondence / compliance / claims | Jim / Toby / Meredith |
| Judge chamber | Judge / arbiter | Oscar / Stanley |
| Boss office | Escalation + human review | Michael |
| Report / archive | Reporter / archivist | Ryan / Creed |

Maroon and gold chrome, cream SNES panels, ink that is never pure black. Tiles and sprites are original — LimeZu maps from Munder Difflin are **not** bundled.

## API

Same producer shape as llm-mailroom. Prefer `/v1`.

| Method | Path | Role |
|---|---|---|
| `GET` | `/v1/health` | Liveness + provider lamp |
| `POST` | `/v1/upload` | Queue a document (202) |
| `POST` | `/v1/topics` | `action=queue` parks a brief; `action=launch` delivers it to a desk |
| `POST` | `/v1/topics/{id}/launch` | Dispatch a queued topic onto the floor |
| `POST` | `/v1/topics/{id}/complete` | Mark a live topic done |
| `GET` | `/v1/topics` | Queue + live + done briefs |
| `POST` | `/v1/demo` | Drop fixture samples on the floor |
| `GET` | `/v1/status/{doc_id}` | Catalog row |
| `GET` | `/v1/audit/{doc_id}` | Hash-chained trail + validity |
| `GET` | `/v1/review/queue` | Human siding |
| `POST` | `/v1/review/{doc_id}/resolve` | `resume` / `record` / `requeue` / `complete` |
| `GET` | `/v1/floor` | Office snapshot |
| `GET` | `/v1/hive` | Roster + inboxes |
| `WS` | `/ws` | Live pipeline + hive events |

## Tests

```bash
pytest -q
```

Tests never call a hosted LLM. The mock sorter/specialists are deterministic over `fixtures/samples/`.

## Layout

```
src/agent_mailroom/   pipeline, agents, hive, storage, API
office/               pixel floor (vanilla JS, no build step)
fixtures/samples/     HarborPoint demo pile
tests/                routing, audit chain, e2e, API
docs/ARCHITECTURE.md  contracts and data flow
```

## License

MIT for original code. Parody office aesthetic; not affiliated with NBC or Dunder Mifflin. See [LICENSE](LICENSE).
