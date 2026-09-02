<div align="center">

# 💾 Storage Backend

**Storage backend for the agent-mailroom package.**

</div>

---

## Purpose

The storage module provides persistence:
- Mail queue storage
- Agent state persistence
- Floor state snapshots
- Audit trail logging

## Usage

```python
from agent_mailroom.storage import Storage

storage = Storage()
storage.save_mail(mail)
storage.load_agent(agent_id)
```

## Related Files

- `../agents/` — Agent implementations
- `../pipeline/` — Pipeline logic
- `../schemas/` — Data schemas
