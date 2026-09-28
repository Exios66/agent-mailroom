<div align="center">

# 👤 Operator Interface

**Operator interface for the agent-mailroom package.**

</div>

---

## Purpose

The operator interface provides human oversight:
- Agent monitoring
- Floor state inspection
- Manual intervention
- Configuration changes

## Usage

Operator login is mounted at `/v1/auth` (`login`, `me`, `logout`). The
operator SQLite DB (`<MAILROOM_BASE_DIR>/operator.db`, or
`MAILROOM_OPERATOR_DB`) is migrated at startup; the first run seeds
`MAILROOM_OPERATOR_USER` / `MAILROOM_OPERATOR_PASSWORD`.

On a public bind, login is refused (503) while `MAILROOM_OPERATOR_JWT_SECRET`
is unset or the seeded password is still the default.

## Related Files

- `../agents/` — Agent implementations
- `../pipeline/` — Pipeline logic
- `../api/` — API endpoints
