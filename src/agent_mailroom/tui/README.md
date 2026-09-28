<div align="center">

# 💻 Terminal UI

**Terminal user interface for the agent-mailroom package.**

</div>

---

## Purpose

The TUI provides a terminal-based interface:
- Floor visualization
- Agent status display
- Mail queue monitoring
- Manual intervention

## Usage

```bash
pip install -e ".[tui]"
MAILROOM_API_URL=http://127.0.0.1:8000 mailroom-tui
```

Send `MAILROOM_API_TOKEN` when the API requires one.

## Related Files

- `../agents/` — Agent implementations
- `../pipeline/` — Pipeline logic
- `../operator/` — Operator interface
