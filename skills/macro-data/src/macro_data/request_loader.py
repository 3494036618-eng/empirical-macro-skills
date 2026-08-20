"""Load the authoritative structured research request contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from macro_data.contracts import validate_document


def load_request_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"request JSON is invalid: {exc}") from exc
    if not isinstance(document, dict):
        raise TypeError("request JSON must contain an object")
    validate_document("request", document)
    return document
