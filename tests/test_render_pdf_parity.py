"""hub#62: render_pdf_pages parity guard — the vision renderer must not
silently diverge between agent-mailroom and its upstream llm-mailroom mirror.

Both packages implement the same ``render_pdf_pages(file_path, cap, dpi)``
signature (the issue's duplication finding). They cannot import each other
(standalone constellation mirrors), so the consolidation contract is:
byte-for-byte behavioral parity enforced by this source-normalization guard.

If you change one implementation, change the other in the same commit — the
test compares the two function bodies after stripping comments, docstrings,
and blank lines.
"""

from __future__ import annotations

import re
from pathlib import Path

_AGENT_VISION = Path(__file__).resolve().parents[1] / "src/agent_mailroom/llm/vision.py"
_UPSTREAM_VISION = (
    Path(__file__).resolve().parents[1].parent
    / "llm-mailroom/src/llm/vision.py"
)

_BODY_RE = re.compile(
    r"^def render_pdf_pages\(.*?\):.*?(?=^def |\Z)",
    re.MULTILINE | re.DOTALL,
)

_COMMENT_RE = re.compile(r"^\s*#.*$", re.MULTILINE)
_DOCSTRING_RE = re.compile(r'""".*?"""|^\s*#.*$', re.MULTILINE | re.DOTALL)
_NONCODE_RE = re.compile(r"[^a-z0-9_=.,()\[\]:\s]", re.MULTILINE)
# Structlog (upstream) passes context as kwargs; stdlib (agent) as extra={...}.
# Normalize the log-call arguments away — only the message matters for parity.
_LOG_CALL_RE = re.compile(r"(?:log|logger)\.(?:debug|info|warning|exception)"
                          r"\(\s*(\"[^\"]*\"|'[^']*')\s*[^)]*\)")


def _normalize_log_calls(body: str) -> str:
    return _LOG_CALL_RE.sub(r"LOGGER.\1()", body)


def _render_pdf_pages_body(path: Path) -> str:
    """Return the render_pdf_pages body normalized for comparison."""
    text = path.read_text(encoding="utf-8")
    match = _BODY_RE.search(text)
    assert match is not None, f"render_pdf_pages not found in {path.name}"
    body = match.group(0)
    body = _DOCSTRING_RE.sub("", body)
    body = _COMMENT_RE.sub("", body)
    body = _normalize_log_calls(body)
    body = re.sub(r"\b(log|logger)\b", "LOGGER", body)
    body = _NONCODE_RE.sub("", body)
    return re.sub(r"\s+", "", body)


def test_render_pdf_pages_matches_upstream():
    """agent-mailroom's render_pdf_pages stays semantically identical to
    llm-mailroom's — a divergent edit fails CI here (hub#62)."""
    if not _UPSTREAM_VISION.exists():
        import pytest

        pytest.skip("llm-mailroom checkout not present next to agent-mailroom")
    agent_body = _render_pdf_pages_body(_AGENT_VISION)
    upstream_body = _render_pdf_pages_body(_UPSTREAM_VISION)
    assert agent_body == upstream_body, (
        "render_pdf_pages drifted from the llm-mailroom upstream. Edit both "
        "implementations in the same commit (hub#62 consolidation)."
    )