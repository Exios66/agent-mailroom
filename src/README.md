<div align="center">

# 📁 Agent Mailroom Source

**Source code for the agent-mailroom package.**

</div>

---

## Structure

| Path | Contents |
|:---|:---|
| [`agent_mailroom/`](agent_mailroom/) | Main package |
| `agent_mailroom/agents/` | Agent implementations |
| `agent_mailroom/api/` | API endpoints |
| `agent_mailroom/config/` | Configuration |
| `agent_mailroom/hive/` | Hive coordination |
| `agent_mailroom/llm/` | LLM client |
| `agent_mailroom/observability/` | Observability |
| `agent_mailroom/operator/` | Operator interface |
| `agent_mailroom/pipeline/` | Pipeline logic |
| `agent_mailroom/schemas/` | Data schemas |
| `agent_mailroom/storage/` | Storage backend |
| `agent_mailroom/tui/` | Terminal UI |

## Usage

```python
from agent_mailroom.agents import WalkingAgent
from agent_mailroom.pipeline import FloorPipeline
```

## Related Files

- `tests/` — Test suites
- `office/` — Office floor assets
- `fixtures/` — Test fixtures
