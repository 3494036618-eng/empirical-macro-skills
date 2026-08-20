from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any, cast

from macro_data.observation_matrix import build_expected_matrix
from macro_data.primary_cell_ledger import (
    LockedObservation,
    PrimaryCellLedger,
)
from macro_data.source_router import RoutePlan

ROOT = Path(__file__).resolve().parents[1]
REQUEST_FIXTURE = ROOT / "fixtures" / "completion" / "request.valid.json"


def _request(
    *,
    start: str = "2019",
    end: str = "2021",
    frequency: str = "A",
    mode: str = "allow_official_missing_only",
) -> dict[str, Any]:
    document = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    request = cast(dict[str, Any], copy.deepcopy(document))
    request["time_range"] = {"start": start, "end": end}
    request["frequency"] = frequency
    request["fallback_policy"]["mode"] = mode
    if mode == "never":
        request["fallback_policy"]["allowed_sources"] = []
        request["preferred_sources"] = ["datapro"]
    return request


def _primary_locked(
    *,
    request: dict[str, Any],
    periods: tuple[str, ...],
) -> PrimaryCellLedger:
    matrix = build_expected_matrix(request)
    selected = [cell for cell in matrix.cells if cell.key.period in periods]
    locked = tuple(
        LockedObservation(
            cell_id=cell.cell_id,
            key=cell.key,
            value=100.0,
            retrieval_provider="datapro",
            source_system="WORLD_BANK",
            dataset_id="2",
            native_series_key=(
                "WORLD_BANK|World Development Indicators|CHN|FP.CPI.TOTL"
            ),
            canonical_series_id="macro-series-" + "a" * 32,
            origin_role="datapro_primary",
            raw_artifact="raw/batch-1.json",
            raw_checksum="sha256:" + "b" * 64,
            retrieved_at="2026-08-18T00:00:00Z",
            item={},
        )
        for cell in selected
    )
    return PrimaryCellLedger(
        matrix_id=matrix.matrix_id,
        locked=locked,
        rejected=(),
        issue_codes=(),
    )


def _plan(*, mode: str, connector: bool = True) -> RoutePlan:
    return RoutePlan(
        primary="datapro",
        fallback_mode=mode,
        fallback_candidates=["world_bank"] if connector else [],
        review_required=mode == "ask",
    )


def _module() -> Any:
    return importlib.import_module("macro_data.residual_gap")


def test_official_request_excludes_datapro_locked_cells() -> None:
    module = _module()
    request = _request()
    matrix = build_expected_matrix(request)
    primary = _primary_locked(request=request, periods=("2019", "2021"))

    manifest = module.build_residual_gaps(
        request=request,
        matrix=matrix,
        primary=primary,
        route_plan=_plan(mode="allow_official_missing_only"),
    )

    assert [cell.key.period for cell in manifest.gap_cells] == ["2020"]
    assert manifest.official_requests[0].periods == ("2020",)
    assert set(manifest.datapro_locked_cell_ids).isdisjoint(
        cell.cell_id for cell in manifest.gap_cells
    )


def test_non_contiguous_gaps_become_separate_official_requests() -> None:
    module = _module()
    request = _request()

    manifest = module.build_residual_gaps(
        request=request,
        matrix=build_expected_matrix(request),
        primary=_primary_locked(request=request, periods=("2020",)),
        route_plan=_plan(mode="allow_official_missing_only"),
    )

    assert [item.periods for item in manifest.official_requests] == [
        ("2019",),
        ("2021",),
    ]


def test_quarterly_gap_uses_the_matrix_canonical_period() -> None:
    module = _module()
    request = _request(start="2010-Q1", end="2010-Q2", frequency="Q")

    manifest = module.build_residual_gaps(
        request=request,
        matrix=build_expected_matrix(request),
        primary=_primary_locked(request=request, periods=("2010Q1",)),
        route_plan=_plan(mode="allow_official_missing_only"),
    )

    assert manifest.official_requests[0].periods == ("2010Q2",)
    assert manifest.official_requests[0].research_request["time_range"] == {
        "start": "2010-Q2",
        "end": "2010-Q2",
    }


def test_never_mode_produces_no_official_request() -> None:
    module = _module()
    request = _request(mode="never")

    manifest = module.build_residual_gaps(
        request=request,
        matrix=build_expected_matrix(request),
        primary=_primary_locked(request=request, periods=()),
        route_plan=_plan(mode="never"),
    )

    assert manifest.official_requests == ()
    assert "fallback_disabled" in manifest.issue_codes


def test_ask_mode_requires_approval_before_request() -> None:
    module = _module()
    request = _request(mode="ask")

    manifest = module.build_residual_gaps(
        request=request,
        matrix=build_expected_matrix(request),
        primary=_primary_locked(request=request, periods=()),
        route_plan=_plan(mode="ask"),
    )

    assert manifest.official_requests == ()
    assert "fallback_approval_required" in manifest.issue_codes


def test_connector_unavailable_keeps_gap_unresolved() -> None:
    module = _module()
    request = _request()

    manifest = module.build_residual_gaps(
        request=request,
        matrix=build_expected_matrix(request),
        primary=_primary_locked(request=request, periods=()),
        route_plan=_plan(mode="allow_official_missing_only", connector=False),
    )

    assert manifest.official_requests == ()
    assert "connector_unavailable" in manifest.issue_codes


def test_complete_datapro_matrix_needs_no_official_connector() -> None:
    module = _module()
    request = _request()

    manifest = module.build_residual_gaps(
        request=request,
        matrix=build_expected_matrix(request),
        primary=_primary_locked(
            request=request,
            periods=("2019", "2020", "2021"),
        ),
        route_plan=_plan(
            mode="allow_official_missing_only",
            connector=False,
        ),
    )

    assert manifest.gap_cells == ()
    assert manifest.official_requests == ()
    assert manifest.issue_codes == ()
