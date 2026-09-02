<div align="center">

# 📐 Data Schemas

**Data schemas for the agent-mailroom package.**

</div>

---

## Schemas

| Schema | Purpose |
|:---|:---|
| `Mail` | Mail item data |
| `Agent` | Agent state |
| `Floor` | Floor layout |
| `Desk` | Desk position |

## Usage

```python
from agent_mailroom.schemas import Mail, Agent

mail = Mail(id="mail-001", sender="alice", recipient="bob")
agent = Agent(name="alice", desk_id="desk-001")
```

## Related Files

- `../agents/` — Agent implementations
- `../pipeline/` — Pipeline logic
