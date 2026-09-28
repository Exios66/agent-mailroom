<div align="center">

# 🧪 Agent Mailroom Tests

**Test suites for the agent-mailroom package.**

</div>

---

## Running Tests

```bash
pip install -e ".[dev]"
python -m pytest tests -q
```

In the Digital-Mailroom monorepo: `uv run pytest packages/agent-mailroom/tests`.

Tests never call a hosted LLM (`MAILROOM_LLM_PROVIDER=mock`) and run with
`MAILROOM_SYNC=1` so the inbox drains in-request. `conftest.py` isolates
`MAILROOM_BASE_DIR` per test and pins a loopback `MAILROOM_HOST`.

## Test Structure

- `test_pipeline_e2e.py`, `test_routing.py`, `test_conflicts.py` — graph + routing
- `test_mailroom_desks.py`, `test_tier_b_desks.py`, `test_tier_c_features.py` — trays, review, scoring pin
- `test_api.py`, `test_security.py` — REST surface, CSP, Electron guards
- `test_watcher.py`, `test_intake.py`, `test_hf_corpora.py`, `test_topics.py` — intake paths
- `test_tiles.py`, `test_render_pdf_parity.py` — LimeZu floor + vision rendering
- `test_v060_residuals.py`, `test_v030_audit.py` — release regression suites

## Related Files

- `src/` — Source code
- `fixtures/` — Test fixtures
- `office/` — Office floor assets
