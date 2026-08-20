from __future__ import annotations

from pathlib import Path

from scripts.quick_validate import _schema_inventory_errors

EXPECTED_SCHEMAS = {
    "macro-data-handoff.schema.json",
    "research-plan-handoff.schema.json",
    "shock-identification-artifact.schema.json",
    "time-series-diagnostics.schema.json",
    "time-series-dynamics-request.schema.json",
    "time-series-dynamics-result.schema.json",
    "time-series-input-evidence-manifest.schema.json",
    "time-series-run-manifest.schema.json",
}


def test_schema_inventory_requires_the_frozen_contract_set(tmp_path: Path) -> None:
    paths = [tmp_path / name for name in sorted(EXPECTED_SCHEMAS)]
    assert _schema_inventory_errors(paths) == []

    missing = [path for path in paths if path.name != "macro-data-handoff.schema.json"]
    assert _schema_inventory_errors(missing) == [
        "missing JSON Schema: macro-data-handoff.schema.json"
    ]

    extra = [*paths, tmp_path / "unexpected.schema.json"]
    assert _schema_inventory_errors(extra) == [
        "unexpected JSON Schema: unexpected.schema.json"
    ]
