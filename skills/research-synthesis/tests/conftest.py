from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def load_json(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} 必须包含 JSON object")
    return cast(dict[str, object], document)


@pytest.fixture
def valid_request() -> dict[str, object]:
    return load_json(FIXTURES / "synthetic" / "request.valid.json")


@pytest.fixture
def adapter_capabilities() -> dict[str, object]:
    return load_json(
        FIXTURES / "synthetic" / "adapter-capabilities.json"
    )
