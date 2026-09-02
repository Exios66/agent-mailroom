<div align="center">

# 🔄 Pipeline Logic

**Pipeline logic for the agent-mailroom package.**

</div>

---

## Purpose

The pipeline module orchestrates the mail processing workflow:
- Mail intake and sorting
- Agent dispatch
- Delivery tracking
- Completion handling

## Usage

```python
from agent_mailroom.pipeline import FloorPipeline

pipeline = FloorPipeline()
pipeline.process_mail(mail)
```

## Related Files

- `../agents/` — Agent implementations
- `../hive/` — Hive coordination
- `../storage/` — Storage backend
