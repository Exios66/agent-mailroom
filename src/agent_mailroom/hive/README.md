<div align="center">

# 🐝 Hive Coordination

**Hive coordination for the agent-mailroom package.**

</div>

---

## Purpose

The hive module coordinates multiple agents on the office floor:
- Agent discovery and registration
- Mail routing between agents
- Floor state synchronization
- Conflict resolution

## Usage

```python
from agent_mailroom.hive import Hive

hive = Hive()
hive.register_agent(agent)
hive.route_mail(sender, recipient, mail)
```

## Related Files

- `../agents/` — Agent implementations
- `../pipeline/` — Pipeline logic
- `../storage/` — Storage backend
