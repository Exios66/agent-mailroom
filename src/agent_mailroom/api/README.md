<div align="center">

# 🔌 Agent Mailroom API

**API endpoints for the agent-mailroom package.**

</div>

---

## Endpoints

| Endpoint | Purpose |
|:---|:---|
| `/api/agents` | Agent status and control |
| `/api/floor` | Office floor state |
| `/api/mail` | Mail queue operations |

## Usage

```bash
cd packages/agent-mailroom
uv run python -m agent_mailroom.api
```

## Related Files

- `../agents/` — Agent implementations
- `../pipeline/` — Pipeline logic
- `../storage/` — Storage backend
