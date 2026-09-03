<div align="center">

# 🧠 LLM Client

**LLM client for the agent-mailroom package.**

</div>

---

## Purpose

The LLM client provides language model integration for agents:
- Prompt management
- Response parsing
- Token counting
- Provider abstraction

## Usage

```python
from agent_mailroom.llm import LLMClient

client = LLMClient(provider="openrouter")
response = client.generate(prompt="Sort this mail...")
```

## Related Files

- `../agents/` — Agent implementations
- `../config/` — Configuration
