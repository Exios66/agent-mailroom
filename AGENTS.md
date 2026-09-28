# AGENTS.md — agent-mailroom

The llm-mailroom document pipeline running on a walking pixel office.
FastAPI + SQLite + filesystem bins. The office is a vanilla-JS SPA in
`office/` (no build step, no npm). Python 3.11+.

## Commands

```bash
pip install -e ".[dev]"            # + [pdf] [vision] [auth] [tui] [observability] as needed
python -m pytest tests -q          # never calls a hosted LLM (mock provider)
python -m agent_mailroom           # API + office on 127.0.0.1:8000
python -m agent_mailroom --desktop # hardened Electron shell (optional)
docker compose up --build          # loopback publish, named data volume
python scripts/eval_pipeline.py --golden golden.json
```

- No linter, formatter or typechecker is configured, so don't invent one.
- The office has no JS test framework. Verify UI changes in a browser
  (Playwright/Chromium). Check 1440, 1024 and 390 px, light and dark, zero
  console errors, and a keyboard-only pass.

## Upstream mirror (the #1 maintenance duty)

llm-mailroom is authoritative. This repo mirrors **0.7.1 @959bb0b**:

- `src/agent_mailroom/config/taxonomy.yaml`
  - doc classes, subclasses and `field_types`
  - agents with their harness keys
  - `llm_retry`, `run_limits`, `cost_models`, the model maps and `by_class`
  - vision models and extensions
- `src/agent_mailroom/agents/prompts.json`: the upstream prompts, copied
  verbatim. `agents/base.py` appends the node output contracts.
- `src/agent_mailroom/schemas/documents.py`: the extraction schemas.
- `src/agent_mailroom/observability/tracing.py`: `NODE_OBSERVATION_TYPES`
  and span names.
- `src/agent_mailroom/pipeline/hf_corpora.py`: the corpus catalog and the
  dataset revision pin (v9.1 = `ed7576b`).
- `pyproject.toml`: the `llm-dojo-scoring` git pin must match llm-mailroom's
  (`v0.16.0`). `tests/test_tier_c_features.py::test_dojo_scoring_pin` locks
  it.

Align with the llm-mailroom taxonomy, not the dojo constants. When upstream
changes, update all of the above in one change, plus the CHANGELOG.

## Contracts that are easy to break

- Review resolve mirrors llm-mailroom:
  - `disposition=complete` requires `decision=approved`.
  - Reject is sent as `rejected` + `resume`.
  - `record` and `requeue` work on any stage; the rest need a parked
    review file.
- Only uploads, the demo, topics and Hub pulls write to the inbox. The
  watcher is the only thing that runs documents. `MAILROOM_SYNC=1` (tests)
  drains in-request.
- Paths:
  - Bins accept only `safe_slug(matter_id)` and taxonomy doc types.
  - `doc_id` must match `valid_doc_id`.
  - Never build a bin path from raw request input.
- Security:
  - A public bind fails closed: no token means 503 unless
    `MAILROOM_ALLOW_OPEN=1`.
  - Keep `api/security.py` `OFFICE_CSP`, `office/index.html` (whose meta
    copy omits `frame-ancestors`) and `electron/security.js` in lockstep.
  - `office/index.html` must keep exactly one `<script>` tag and the
    `data-testid` / `data-tab` hooks that `tests/test_security.py` and
    `tests/test_tiles.py` assert.
- Every route lives under `/v1`. `/health` is the only bare alias.

## Monorepo

This repo is also `packages/agent-mailroom` in
[Digital-Mailroom](https://github.com/LLM-Mailroom-Services/Digital-Mailroom).

- Standalone work flows in with `scripts/sync_packages.py pull --squash`,
  run at the monorepo root.
- The monorepo re-adds its `[tool.uv.sources]` workspace override. That
  override is a monorepo-only adaptation, so don't commit it here.

## Assets

The LimeZu Modern Interiors tilesets in `office/tiles/` are **not** MIT (see
`LIMEZUASSETS-LICENSE.txt`). Keep the credit link visible. Redistribution
terms are the maintainer's call. Don't change or remove the assets without
asking.

## Release

Semver in `pyproject.toml`, `src/agent_mailroom/__init__.py` and the FastAPI
app version. `tests/test_v030_audit.py::test_version_strings_agree` locks
these together. Keep a Changelog entries go under `## [Unreleased]` and move
to `## [X.Y.Z] - date` on release. Tag `vX.Y.Z` on the merged release
commit.
