<div align="center">

# ⚙️ Agent Mailroom Scripts

**Utility scripts for the agent-mailroom package.**

</div>

---

## Scripts

| Script | Purpose |
|:---|:---|
| `eval_pipeline.py` | Score archived extractions against a golden JSON file, per document class |

## Usage

```bash
python scripts/eval_pipeline.py --golden golden.json --limit 50
```

`golden.json` maps a `doc_id` or original filename to the expected fields;
an entry may pin `"doc_type"` to score with that class's field map.

## Related Files

- `src/` — Source code
- `office/` — Office floor assets
- `tests/` — Test suites
