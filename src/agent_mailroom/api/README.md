<div align="center">

# 🔌 Agent Mailroom API

**API endpoints for the agent-mailroom package.**

</div>

---

## Endpoints

Every route lives under `/v1` (plus a bare `/health` probe alias and the
`/ws` live stream). The full table is in the top-level README.

| Module | Purpose |
|:---|:---|
| `app.py` | FastAPI app, lifespan (bins, catalog, operator DB, hive, watcher), `/ws` auth + Origin check |
| `routes.py` | Producer routes: upload, review resolve, trays, floor, ops, topics, datasets |
| `present.py` | Catalog rows → floor/tray views (one tray scan per request) |
| `security.py` | CSP + hardening headers, public-bind / Origin helpers |
| `ws.py` | Event hub broadcasting pipeline + hive events |

## Usage

```bash
python -m agent_mailroom            # API + office on 127.0.0.1:8000
```

A non-loopback `MAILROOM_HOST` without `MAILROOM_API_TOKEN` fails closed
(503) unless `MAILROOM_ALLOW_OPEN=1`.

## Related Files

- `../agents/` — Agent implementations
- `../pipeline/` — Pipeline logic
- `../storage/` — Storage backend
