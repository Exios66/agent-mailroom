# Architecture

Agent Mailroom is a self-contained hybrid:

- **Pipeline** — the llm-mailroom document state machine (classify → extract → judge → report → archive), including filesystem bins, a SQLite catalog, and a SHA-256 hash-chained audit log.
- **Hive** — Munder-style atomic mailboxes. Agents write JSON to `outbox/`; the router delivers to `inbox/` and the office draws a flying envelope.
- **Office** — an original pixel floor (no LimeZu tilesets) with procedural sitcom-cast avatars, SNES chrome, and maroon/gold Dunder-Mifflin branding.

Uploads, demo piles, and filing-like topics **only write the inbox** (plus a `.meta` sidecar). The embedded watcher claims each file into `processing/` and runs the graph once. `MAILROOM_SYNC=1` drains the inbox in-request so tests stay deterministic. Do not call the runner on a file that is still sitting in the inbox — that double-runs.

```
upload / demo / topic ingest / drop
    │
    ▼
inbox bin + sidecar ──► watcher claim ──► ingest ──► sorter (Pam)
                 │
                 ├── high confidence ──► specialist desk (Dwight / Angela / Jim / Toby / Meredith)
                 ├── medium band ──► Kelly second opinion ──► extract or review
                 └── unknown / exhausted ──► Michael's office (human review)
                                │
                                ▼
                         judge (Oscar) ──► arbiter (Stanley) ──► reporter (Ryan) ──► Creed's archive
```

Routing thresholds live in [`src/agent_mailroom/config/taxonomy.yaml`](../src/agent_mailroom/config/taxonomy.yaml). They are not hardcoded.

The office is static files under `office/` served by the same FastAPI process. Live updates go over `/ws`. The display contract (`stage`, `doc_type`, review dispositions) matches The-Mailroom / llm-mailroom so this repo can sit at the center of that constellation.

**Live topics.** Operators can **queue** or **launch** briefs while the floor is running.

- `POST /v1/topics` with `action=queue` parks a row (`status=queued`). No hive mail yet.
- `POST /v1/topics` with `action=launch`, or `POST /v1/topics/{id}/launch`, delivers a hive `request` to the chosen desk (default: the boss), appends `hive/board.md`, and — if the body looks like a filing — drops it into the inbox so the pipeline runs it.
- `POST /v1/topics/{id}/complete` marks the brief done.

The Topics tab is the command-center composer for both paths.
