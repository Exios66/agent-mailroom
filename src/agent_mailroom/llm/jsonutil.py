from __future__ import annotations

import json
from typing import Any


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a model reply that should be a JSON object, including fenced dumps."""
    blob = (text or "").strip()
    if blob.startswith("```"):
        blob = blob.strip("`")
        if blob.lower().startswith("json"):
            blob = blob[4:].strip()
    try:
        data = json.loads(blob)
        if isinstance(data, dict):
            return data
        raise ValueError("JSON root is not an object")
    except json.JSONDecodeError:
        start = blob.find("{")
        end = blob.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(blob[start : end + 1])
            if isinstance(data, dict):
                return data
        raise
