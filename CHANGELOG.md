# Changelog

All notable changes to Agent Mailroom are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-09-28

Upstream resync to llm-mailroom 0.7.1 @959bb0b / llm-dojo-scoring v0.16.0 /
mailroom-dataset v9.1, a full audit (loud and quiet bugs, security), and a
visual redesign of the office.

### Added
- `merger_agreement_specialist` (Toby, `desk-merger`) with
  `MergerAgreementExtraction`, a HarborPoint merger fixture, and the mock
  MAUD extraction.
- `agents/prompts.json`: the upstream prompts copied verbatim, plus
  per-node output-contract suffixes; the sorter prompt renders the live
  class descriptions and CUAD subtypes.
- Taxonomy mirror of 0.7.1: per-agent provider / model / temperature /
  `max_tokens` / `max_input_chars` / `reasoning_effort`, `llm_retry`,
  `run_limits`, dict-form `cost_models`, vllm / ollama / llamafile model
  maps, the 12 accepted file extensions, vision models, per-class
  `field_types` and descriptions, and v9.1 subclass vocabularies.
- The `document-pipeline` root trace, plus `route-for-review`,
  `write-catalog` and `archive-document` spans. `adjudicate-conflict` is
  typed as an agent (`NODE_OBSERVATION_TYPES` mirror).
- Dataset pin `CORPUS_REVISION = "v9.1"` (`ed7576b`), train/test splits,
  and the aliases `v8`, `v9`, `v9.1` and `mailroom-dataset`.
- Fail-closed public binds: a non-loopback `MAILROOM_HOST` without
  `MAILROOM_API_TOKEN` returns 503 unless `MAILROOM_ALLOW_OPEN=1`. Operator
  login refuses the default JWT secret or the seeded password on a public
  bind.
- `/ws` token and Origin checks.
- `GET /v1/health` runs a real catalog probe (`status: down` on failure).
- `MAILROOM_OFFICE_DIR` / `MAILROOM_FIXTURES_DIR` for non-editable
  installs. `eval_pipeline.py` now reports `by_class`.
- Office: an "On the floor" keyboard list mirroring the canvas, toasts, an
  `aria-live` status line, per-action busy/done/error states, a
  keyboard-reachable Upload, ARIA tabs with arrow-key navigation, and dark
  mode.
- `tests/test_v030_audit.py`: 31 regression tests.

### Changed
- `compliance_filing` is retired everywhere: classes, schemas, the mock,
  `by_class`, UI class lists and fixtures.
- The dojo pin moves to `v0.16.0`. The monorepo-only `[tool.uv.sources]`
  override is dropped from the standalone `pyproject.toml`.
- `MAILROOM_LLM_PROVIDER` now beats the taxonomy provider. Local providers
  map the OpenRouter model id; the Ollama default is `qwen3:7b`.
- LLM calls honour temperature and `max_tokens`, and send `reasoning.effort`
  to OpenRouter. They retry with backoff and jitter; non-transient 4xx
  errors are not retried.
- Judge, arbiter and boss get real context: source text, extracted JSON,
  and `CONFLICT=yes/no`. A retry extract sends `FIELDS_TO_FIX` /
  `JUDGE_FINDINGS`.
- The router is mounted once under `/v1`, and the bare 0.2.x aliases are
  gone. `GET /health` stays as a probe alias.
- `/v1/datasets/pull` only enqueues, and the watcher claims the rows.
  `MAILROOM_SYNC=1` keeps the inline drain.
- Review resolve follows the llm-mailroom contract:
  - `decision` and `disposition` are validated.
  - A class override is checked against the taxonomy and the subclass
    catalog.
  - `record` merges into the stored row.
  - `requeue` closes the parked row as superseded and removes the parked
    file.
  - Only `approved` resumes; resume failures are reported.
- Office redesign: new tokens, with Inter at 12px or larger for everything
  people read. Tabs wrap to their own row instead of scrolling out of view.
  The canvas uses integer scaling when it fits and fills the column
  otherwise. The legend moves into the side panel. The poll fetches the
  floor and status plus only the visible panel.
- Compose publishes on `127.0.0.1` and uses a named data volume. The
  Dockerfile installs git (needed for the dojo git pin).

### Fixed
- LLM failures no longer become "extractions". `run_agent` stopped
  swallowing `LLMError`, and hard aborts reach the failed bin with a
  `failure_class`.
- The judge gate fails closed: a missing verdict routes to human review.
- Path traversal: `matter_id`, `doc_type` and `doc_id` can no longer
  escape the bins. Glob characters in ids are rejected.
- `/v1/floor`, `/v1/hive`, `/v1/console` and `POST /v1/demo` ignored the
  API token.
- The Langfuse `observation` / `pipeline_trace` context managers swallowed
  body exceptions and yielded twice ("generator didn't stop after
  throw()"). They also passed an invalid `name=` kwarg to the logger.
- `span_context` dropped the span of a node that raised.
- Stuck detection compared ISO timestamps as text against SQLite's format,
  so it never matched. The masking test fixture is fixed too.
- `recover_stuck` requeued without the `.meta` sidecar, so the doc got a
  new id and a DEFAULT matter. It also requeued classified snapshots.
- The watcher leaked `_claimed` keys on its early return. Its heartbeat
  went "stale" during long runs.
- The safety cap left runs stuck in `processing`. They now park on review.
- Resume copied the parked file, so a leftover review copy made the
  document look parked again after it archived.
- The Reject button always got a 400: it sent `rejected` + `complete`.
- Every `with connect()` leaked a SQLite connection. `init_db` ran on every
  read.
- Operator logout before any login failed with "no such table: ui_audit".
- `/floor` rescanned every bin for each row.
- GET routes wrote the trace cache.
- `registry.json` writes were not atomic.
- The source pane decoded raw PDF bytes, and the source endpoint read files
  twice.
- Vision `doc.close()` was skipped on errors.
- Hub query parameters were not URL-encoded.
- `get_extraction_schema` raised `KeyError` for unknown types. Money fields
  now accept "$12,500.00" strings, and a stated `0` counts as a value.
- A configured `0` (retry delay, budgets) was replaced by the default.
- The field-type map mutated the shared per-class dict.
- `eval_pipeline.py` scored every document as a contract.
- The Electron navigation guard matched `127.0.0.1:8000.evil.example` by
  string prefix and allowed any loopback port.
- Office: Replay read the wrong payload level and flew a blank envelope.
- Office: the Providers table printed the harness name twice and never
  showed the models.
- Office: Recover claimed filings were "moved to review".
- Office: topic routes listed only 7 of the 12 desks.
- Office: some interpolations were not escaped, and topic bodies were
  sliced after escaping.
- Office: envelope hit-testing ignored the flight arc. Tray badges counted
  only recent runs. Bubble widths were estimated rather than measured.
- Office: the meta CSP carried `frame-ancestors`, which browsers ignore
  there and log as an error.

## [0.2.0]

- Sync to llm-mailroom v0.7.x, LimeZu office floor, operator desks,
  Hub dataset pulls, topics, Electron shell.
