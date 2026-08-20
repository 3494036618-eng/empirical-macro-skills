from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from macro_data.observation_matrix import build_expected_matrix

ROOT = Path(__file__).resolve().parents[1]
REQUEST_FIXTURE = ROOT / "fixtures" / "completion" / "request.valid.json"


def _request() -> dict[str, Any]:
    document = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    return cast(dict[str, Any], document)


def _item(
    *,
    entity: str = "CHN",
    indicator: str = "FP.CPI.TOTL",
    period: str = "2019",
    frequency: str = "A",
    value: object = 100.0,
    raw_artifact: str = "raw/batch-1.json",
    raw_checksum: str = "sha256:" + "a" * 64,
) -> dict[str, Any]:
    return {
        "provider": "datapro",
        "retrieval_provider": "datapro",
        "series_key": (
            f"WORLD_BANK|World Development Indicators|{entity}|{indicator}"
        ),
        "source_system": "WORLD_BANK",
        "dataset_id": "2",
        "dataset_name": "World Development Indicators",
        "entity_code": entity,
        "entity_name": "China",
        "indicator_code": indicator,
        "indicator_name": "Consumer price index",
        "time_raw": period,
        "time_grain": "year",
        "observed_frequency": frequency,
        "value": value,
        "unit": {"value": "index", "status": "source_documented"},
        "seasonal_adjustment": {"value": None, "status": "not_applicable"},
        "price_basis": {
            "value": {
                "type": "index",
                "base_period": None,
                "chain_linked": None,
            },
            "status": "source_documented",
        },
        "definition": {
            "value": "Consumer price index",
            "status": "source_provided",
        },
        "release_date": {"value": None, "status": "unresolved"},
        "vintage": {"value": None, "status": "unresolved"},
        "p_date": {"value": "2026-08-18", "semantics": "source_last_updated"},
        "license": {
            "id": "CC-BY-4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "World Bank",
            "use_status": "allowed",
            "allows_requested_use": True,
        },
        "batch_id": "batch-1",
        "raw_artifact": raw_artifact,
        "raw_checksum": raw_checksum,
        "retrieved_at": "2026-08-18T00:00:00Z",
    }


def _evaluation(*items: dict[str, Any]) -> dict[str, Any]:
    return {"selected_items": list(items)}


def _module() -> Any:
    return importlib.import_module("macro_data.primary_cell_ledger")


def test_locks_exact_datapro_cell_with_physical_binding() -> None:
    module = _module()
    request = _request()

    ledger = module.lock_datapro_cells(
        request=request,
        matrix=build_expected_matrix(request),
        evaluation=_evaluation(_item()),
    )

    locked = ledger.locked[0]
    assert locked.retrieval_provider == "datapro"
    assert locked.origin_role == "datapro_primary"
    assert locked.raw_artifact == "raw/batch-1.json"
    assert locked.raw_checksum == "sha256:" + "a" * 64
    assert ledger.by_key()[locked.key] == locked


@pytest.mark.parametrize(
    ("case", "expected_issue"),
    (
        ("wrong_entity", "entity_mismatch"),
        ("wrong_indicator", "indicator_mismatch"),
        ("wrong_frequency", "frequency_mismatch"),
        ("outside_period", "period_outside_matrix"),
        ("non_finite", "non_finite_value"),
        ("unit_unknown", "unit_unknown"),
        ("missing_raw", "raw_artifact_missing"),
        ("invalid_checksum", "raw_checksum_invalid"),
    ),
)
def test_rejects_ineligible_datapro_cell(case: str, expected_issue: str) -> None:
    module = _module()
    item = _item()
    if case == "wrong_entity":
        item["entity_code"] = "USA"
    elif case == "wrong_indicator":
        item["indicator_code"] = "NY.GDP.MKTP.CD"
    elif case == "wrong_frequency":
        item["observed_frequency"] = "Q"
    elif case == "outside_period":
        item["time_raw"] = "2022"
    elif case == "non_finite":
        item["value"] = float("nan")
    elif case == "unit_unknown":
        item["unit"]["status"] = "unresolved"
    elif case == "missing_raw":
        item["raw_artifact"] = ""
    elif case == "invalid_checksum":
        item["raw_checksum"] = "sha256:not-a-hash"

    ledger = module.lock_datapro_cells(
        request=_request(),
        matrix=build_expected_matrix(_request()),
        evaluation=_evaluation(item),
    )

    assert ledger.locked == ()
    assert expected_issue in ledger.rejected[0]["reason_codes"]


def test_same_cell_with_two_values_is_conflicted_not_locked() -> None:
    module = _module()

    ledger = module.lock_datapro_cells(
        request=_request(),
        matrix=build_expected_matrix(_request()),
        evaluation=_evaluation(_item(value=100.0), _item(value=101.0)),
    )

    assert ledger.locked == ()
    assert "datapro_cell_value_conflict" in ledger.issue_codes


def test_locking_does_not_mutate_evaluation() -> None:
    module = _module()
    evaluation = _evaluation(_item())
    before = copy.deepcopy(evaluation)

    module.lock_datapro_cells(
        request=_request(),
        matrix=build_expected_matrix(_request()),
        evaluation=evaluation,
    )

    assert evaluation == before
