from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_mailroom.config.loader import agent_config, taxonomy
from agent_mailroom.llm.client import chat_json

PROMPTS_PATH = Path(__file__).resolve().parent / "prompts.json"

# Upstream system prompts carry the production doctrine; these suffixes pin
# the JSON shape THIS app's graph nodes read (verdict / decision tokens
# differ from llm-mailroom's typed Pydantic outputs).
OUTPUT_CONTRACTS: dict[str, str] = {
    "sorter": (
        'Return one JSON object: {"doc_type": <class key or "unknown">, '
        '"contract_subtype": <CUAD key or null>, "doc_subclass": <catalog key or null>, '
        '"confidence": <0-1>, "reasoning": <one sentence>}.'
    ),
    "sorter_reviewer": (
        'Return one JSON object: {"doc_type": <class key or "unknown">, '
        '"contract_subtype": <key or null>, "doc_subclass": <key or null>, '
        '"confidence": <0-1>, "verdict": "reviewer_agrees_high"|"reviewer_agrees_low"|'
        '"reviewer_overrides", "reasoning": <one sentence>}.'
    ),
    "judge": (
        'Return one JSON object: {"verdict": "complete"|"partial"|"incomplete", '
        '"score": <0-1>, "findings": [<short strings>], '
        '"fields_to_fix": [<registered field names>]}.'
    ),
    "arbiter": (
        'Return one JSON object: {"decision": "accept_with_caveats"|"retry_extraction"|'
        '"human_review", "reasoning": <one sentence>, "fields_to_fix": [<field names>], '
        '"handoff_summary": <string or null>}.'
    ),
    "boss": (
        'Return one JSON object: {"decision": "approved"|"review", "reasoning": <one sentence>}.'
    ),
}
_SPECIALIST_CONTRACT = (
    "Return one JSON object with every registered schema field (unstated values "
    'null or []) plus "confidence" (0-1) and optional "reasoning".'
)


@lru_cache(maxsize=1)
def _prompts() -> dict[str, str]:
    return json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))


def _render_sorter(template: str) -> str:
    """Fill the upstream sorter placeholders from this app's taxonomy."""
    classes = taxonomy().get("doc_classes") or []
    descriptions = "\n".join(
        f"- {row['key']}: {row.get('description') or row.get('label') or row['key']}"
        for row in classes
    )
    contract = next((row for row in classes if row.get("key") == "contract"), {})
    subtypes = "\n".join(
        f"- {key}" for key in (contract.get("subclasses") or []) if key != "other"
    )
    return template.replace("{{doc_type_descriptions}}", descriptions).replace(
        "{{contract_subtypes}}", subtypes
    )


def system_prompt(name: str) -> str:
    """The upstream (llm-mailroom 0.7.1) system prompt plus this app's output
    contract. Unknown agents get a minimal JSON instruction."""
    template = _prompts().get(name)
    if not template:
        return "You are a mailroom agent. Return one JSON object."
    if name in {"sorter", "sorter_reviewer"}:
        template = _render_sorter(template)
    contract = OUTPUT_CONTRACTS.get(name) or (
        _SPECIALIST_CONTRACT if name.endswith("_specialist") else ""
    )
    return f"{template}\n\nOUTPUT CONTRACT (this deployment):\n{contract}" if contract else template


def run_agent(name: str, user: str) -> dict[str, Any]:
    """Call one agent. LLM failures raise ``LLMError`` so the runner can send
    hard aborts to the failed bin — they used to be swallowed into an
    ``unknown`` classification that parked every outage in human review."""
    return chat_json(name, system_prompt(name), user, agent_cfg=agent_config(name))
