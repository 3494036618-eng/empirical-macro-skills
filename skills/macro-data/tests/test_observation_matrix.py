from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE_REQUEST = ROOT / "fixtures" / "completion" / "request.valid.json"


def _request(
    *,
    entities: tuple[str, ...] = ("CHN",),
    indicators: tuple[str, ...] = ("FP.CPI.TOTL",),
    start: str = "2019",
    end: str = "2021",
    frequency: str = "A",
) -> dict[str, Any]:
    document = json.loads(BASE_REQUEST.read_text(encoding="utf-8"))
    request = cast(dict[str, Any], copy.deepcopy(document))
    request["entities"] = [
        {
            "name_or_code": entity,
            "entity_type": "country",
            "code_scheme": "ISO-3166-1-alpha-3",
        }
        for entity in entities
    ]
    request["indicators"] = [
        {
            "name_or_code": indicator,
            "required_definition": f"Definition for {indicator}",
        }
        for indicator in indicators
    ]
    request["time_range"] = {"start": start, "end": end}
    request["frequency"] = frequency
    return request


def _module() -> Any:
    return importlib.import_module("macro_data.observation_matrix")


def test_builds_country_indicator_period_cartesian_product() -> None:
    module = _module()
    request = _request(
        entities=("CHN", "USA"),
        indicators=("FP.CPI.TOTL", "NY.GDP.MKTP.CD"),
        start="2019",
        end="2020",
    )

    matrix = module.build_expected_matrix(request)

    assert len(matrix.cells) == 8
    assert matrix.keys() == {
        module.CanonicalObservationKey(indicator, entity, period, "A")
        for indicator in ("FP.CPI.TOTL", "NY.GDP.MKTP.CD")
        for entity in ("CHN", "USA")
        for period in ("2019", "2020")
    }


@pytest.mark.parametrize(
    ("frequency", "start", "end", "expected_periods"),
    (
        ("Q", "2010-Q1", "2011-Q4", tuple(f"{year}Q{quarter}" for year in (2010, 2011) for quarter in range(1, 5))),
        ("M", "2024-01", "2024-12", tuple(f"2024-{month:02d}" for month in range(1, 13))),
    ),
)
def test_matrix_uses_exact_frequency_periods(
    frequency: str,
    start: str,
    end: str,
    expected_periods: tuple[str, ...],
) -> None:
    module = _module()

    matrix = module.build_expected_matrix(
        _request(start=start, end=end, frequency=frequency)
    )

    assert tuple(cell.key.period for cell in matrix.cells) == expected_periods


def test_matrix_identity_is_order_independent() -> None:
    module = _module()
    first = module.build_expected_matrix(_request(entities=("USA", "CHN")))
    second = module.build_expected_matrix(_request(entities=("CHN", "USA")))

    assert first.matrix_id == second.matrix_id
    assert first.as_document() == second.as_document()
