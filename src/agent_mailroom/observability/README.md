<div align="center">

# 📊 Observability

**Observability module for the agent-mailroom package.**

</div>

---

## Purpose

The observability module provides tracing and metrics:
- Agent action tracing
- Mail delivery metrics
- Floor performance monitoring
- Debug event logging

## Usage

```python
from agent_mailroom.observability import trace_agent_action

with trace_agent_action(agent, "walk"):
    agent.walk_to("mailroom")
```

## Related Files

- `../agents/` — Agent implementations
- `../pipeline/` — Pipeline logic
