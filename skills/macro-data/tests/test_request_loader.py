from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import FIXTURES, load_json

from macro_data.request_loader import load_request_json


def test_loads_valid_structured_request(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text(
        json.dumps(load_json(FIXTURES / "synthetic" / "schema-examples" / "request.valid.json")),
        encoding="utf-8",
    )

    assert load_request_json(path)["schema_version"] == "0.2.0-beta"


def test_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="request JSON is invalid"):
        load_request_json(path)


def test_rejects_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(TypeError, match="must contain an object"):
        load_request_json(path)


def test_rejects_request_contract_violation(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text(
        json.dumps({"schema_version": "0.2.0-beta"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="contract violation"):
        load_request_json(path)
