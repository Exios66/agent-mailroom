<div align="center">

# 🤖 Agent Implementations

**Agent classes for the agent-mailroom package.**

</div>

---

## Agents

| Agent | Purpose |
|:---|:---|
| `WalkingAgent` | Agent that walks the office floor |
| `MailCarrier` | Agent that carries mail between desks |
| `Sorter` | Agent that sorts incoming mail |

## Usage

```python
from agent_mailroom.agents import WalkingAgent

agent = WalkingAgent(name="alice", desk_id="desk-001")
agent.walk_to("mailroom")
```

## Related Files

- `../pipeline/` — Pipeline logic
- `../hive/` — Hive coordination
- `../schemas/` — Data schemas
