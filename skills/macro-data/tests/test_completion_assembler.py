from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from macro_data.observation_matrix import (
    ExpectedObservationMatrix,
    build_expected_matrix,
)
from macro_data.primary_cell_ledger import (
    LockedObservation,
    PrimaryCellLedger,
)
from macro_data.series_mapping import OverlapValidation

ROOT = Path(__file__).resolve().parents[1]
REQUEST_FIXTURE = ROOT / "fixtures" / "completion" / "request.valid.json"


def _matrix(start: str = "2019", end: str = "2020") -> ExpectedObservationMatrix:
    document = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    request = cast(dict[str, Any], copy.deepcopy(document))
    request["time_range"] = {"start": start, "end": end}
    return build_expected_matrix(request)


def _observation(
    matrix: ExpectedObservationMatrix,
    period: str,
    *,
    value: float = 100.0,
    provider: str = "datapro",
    origin_role: str | None = None,
) -> LockedObservation:
    cell = next(cell for cell in matrix.cells if cell.key.period == period)
    role = origin_role or (
        "datapro_primary" if provider == "datapro" else "official_missing_only"
    )
    return LockedObservation(
        cell_id=cell.cell_id,
        key=cell.key,
        value=value,
        retrieval_provider=provider,
        source_system="WORLD_BANK",
        dataset_id="2",
        native_series_key="WORLD_BANK|2|CHN|FP.CPI.TOTL|A",
        canonical_series_id="macro-series-" + "a" * 32,
        origin_role=role,
        raw_artifact=f"raw/{provider}-{period}.json",
        raw_checksum="sha256:" + "b" * 64,
        retrieved_at="2026-08-18T00:00:00Z",
        item={},
    )


def _primary(
    matrix: ExpectedObservationMatrix,
    periods: tuple[str, ...],
) -> PrimaryCellLedger:
    return PrimaryCellLedger(
        matrix_id=matrix.matrix_id,
        locked=tuple(_observation(matrix, period) for period in periods),
        rejected=(),
        issue_codes=(),
    )


def _module() -> Any:
    return importlib.import_module("macro_data.completion_assembler")


def test_fallback_can_never_replace_datapro_cell() -> None:
    module = _module()
    matrix = _matrix("2019", "2019")

    result = module.assemble_completion(
        matrix=matrix,
        primary=_primary(matrix, ("2019",)),
        fallback=(
            _observation(matrix, "2019", value=999.0, provider="world_bank"),
        ),
        overlaps=(),
    )

    assert result.observations[0].value == 100.0
    assert result.observations[0].origin_role == "datapro_primary"
    assert "fallback_attempted_primary_replacement" in result.issue_codes


def test_official_value_fills_only_missing_cell() -> None:
    module = _module()
    matrix = _matrix()

    result = module.assemble_completion(
        matrix=matrix,
        primary=_primary(matrix, ("2019",)),
        fallback=(_observation(matrix, "2020", provider="world_bank"),),
        overlaps=(),
    )

    assert [item.origin_role for item in result.observations] == [
        "datapro_primary",
        "official_missing_only",
    ]
    assert result.residual_gap_count == 0


@pytest.mark.parametrize(
    ("datapro", "official", "expected"),
    (
        (100, 0, "datapro_only"),
        (80, 20, "datapro_primary"),
        (79, 21, "datapro_assisted"),
        (0, 100, "datapro_attempted"),
    ),
)
def test_contribution_classification(
    datapro: int,
    official: int,
    expected: str,
) -> None:
    module = _module()

    assert (
        module.classify_contribution(
            datapro,
            official,
            datapro_attempted=True,
        )
        == expected
    )


def test_complete_exact_matrix_is_research_ready_below_eighty_percent_datapro() -> None:
    module = _module()
    matrix = _matrix("2010", "2019")
    periods = tuple(str(year) for year in range(2010, 2020))

    result = module.assemble_completion(
        matrix=matrix,
        primary=_primary(matrix, periods[:3]),
        fallback=tuple(
            _observation(matrix, period, provider="world_bank")
            for period in periods[3:]
        ),
        overlaps=(),
    )

    assert result.contribution.classification == "datapro_assisted"
    assert result.residual_gap_count == 0
    assert "datapro_primary_threshold_not_met" not in result.issue_codes


def test_validation_overlap_never_enters_estimator_observations() -> None:
    module = _module()
    matrix = _matrix("2019", "2019")

    result = module.assemble_completion(
        matrix=matrix,
        primary=_primary(matrix, ("2019",)),
        fallback=(
            _observation(
                matrix,
                "2019",
                provider="world_bank",
                origin_role="validation_overlap",
            ),
        ),
        overlaps=(
            OverlapValidation(
                status="verified",
                compared_periods=("2019",),
                maximum_absolute_error=0.0,
                maximum_relative_error=0.0,
                issue_codes=(),
            ),
        ),
    )

    assert len(result.observations) == 1
    assert len(result.validation_overlaps) == 1
    assert result.overlap_results[0].status == "verified"


def test_conflicted_overlap_blocks_the_cell_without_replacing_primary() -> None:
    module = _module()
    matrix = _matrix("2019", "2019")

    result = module.assemble_completion(
        matrix=matrix,
        primary=_primary(matrix, ("2019",)),
        fallback=(
            _observation(
                matrix,
                "2019",
                value=101.0,
                provider="world_bank",
                origin_role="validation_overlap",
            ),
        ),
        overlaps=(
            OverlapValidation(
                status="conflicted",
                compared_periods=("2019",),
                maximum_absolute_error=1.0,
                maximum_relative_error=0.01,
                issue_codes=("overlap_value_conflict",),
            ),
        ),
    )

    assert result.observations == ()
    assert result.validation_overlaps[0].value == 101.0
    assert result.conflict_count == 1
    assert result.residual_gap_count == 1
