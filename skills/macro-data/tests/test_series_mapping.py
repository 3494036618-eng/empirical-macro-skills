from __future__ import annotations

import importlib
from typing import Any

from macro_data.observation_matrix import CanonicalObservationKey
from macro_data.primary_cell_ledger import LockedObservation


def _item(
    *,
    provider: str = "datapro",
    source: str = "WORLD_BANK",
    dataset_id: str = "2",
    indicator: str = "FP.CPI.TOTL",
    entity: str = "CHN",
    frequency: str = "A",
    series_key: str | None = None,
) -> dict[str, Any]:
    return {
        "retrieval_provider": provider,
        "source_system": source,
        "dataset_id": dataset_id,
        "dataset_name": "World Development Indicators",
        "series_key": series_key
        or f"{source}|{dataset_id}|{entity}|{indicator}|{frequency}",
        "indicator_code": indicator,
        "entity_code": entity,
        "observed_frequency": frequency,
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
    }


def _observation(
    *,
    period: str = "2020",
    value: float = 100.0,
    provider: str = "datapro",
) -> LockedObservation:
    key = CanonicalObservationKey("FP.CPI.TOTL", "CHN", period, "A")
    return LockedObservation(
        cell_id="macro-cell-" + period.ljust(32, "0"),
        key=key,
        value=value,
        retrieval_provider=provider,
        source_system="WORLD_BANK",
        dataset_id="2",
        native_series_key="WORLD_BANK|2|CHN|FP.CPI.TOTL|A",
        canonical_series_id="macro-series-" + "a" * 32,
        origin_role=(
            "datapro_primary" if provider == "datapro" else "validation_overlap"
        ),
        raw_artifact=f"raw/{provider}.json",
        raw_checksum="sha256:" + "b" * 64,
        retrieved_at="2026-08-18T00:00:00Z",
        item={},
    )


def _module() -> Any:
    return importlib.import_module("macro_data.series_mapping")


def test_same_source_exact_identity_maps_across_retrieval_providers() -> None:
    module = _module()

    mapping = module.resolve_series_mapping(
        _item(provider="datapro"),
        _item(provider="world_bank"),
    )

    assert mapping.status == "exact_native"
    assert mapping.source_system == "WORLD_BANK"


def test_different_source_systems_never_auto_map() -> None:
    module = _module()

    mapping = module.resolve_series_mapping(
        _item(source="IMF", dataset_id="CPI"),
        _item(source="WORLD_BANK", dataset_id="2"),
    )

    assert mapping.status == "rejected"


def test_same_name_with_different_indicator_identity_is_rejected() -> None:
    module = _module()
    primary = _item(indicator="IMF.CPI")
    fallback = _item(indicator="FP.CPI.TOTL")
    primary["indicator_name"] = fallback["indicator_name"] = "Consumer price index"

    mapping = module.resolve_series_mapping(primary, fallback)

    assert mapping.status == "rejected"


def test_explicit_approved_mapping_is_used_when_native_keys_differ() -> None:
    module = _module()
    primary = _item(series_key="WORLD_BANK|legacy|CHN|CPI")
    fallback = _item(series_key="WORLD_BANK|current|CHN|CPI")
    approved = module.SeriesIdentityMapping(
        mapping_id="series-map-" + "c" * 32,
        source_system="WORLD_BANK",
        primary_native_series_key=primary["series_key"],
        fallback_native_series_key=fallback["series_key"],
        canonical_series_id="macro-series-" + "d" * 32,
        status="approved_mapping",
        mapping_version="2026-08-18",
    )

    mapping = module.resolve_series_mapping(primary, fallback, approved=(approved,))

    assert mapping == approved


def test_overlap_within_tolerance_verifies_without_replacement() -> None:
    module = _module()

    validation = module.validate_overlap(
        (_observation(value=100.0),),
        (_observation(value=100.000001, provider="world_bank"),),
        absolute_tolerance=0.00001,
        relative_tolerance=0.0,
    )

    assert validation.status == "verified"
    assert validation.compared_periods == ("2020",)
    assert validation.issue_codes == ()


def test_overlap_above_tolerance_conflicts() -> None:
    module = _module()

    validation = module.validate_overlap(
        (_observation(value=100.0),),
        (_observation(value=101.0, provider="world_bank"),),
        absolute_tolerance=0.00001,
        relative_tolerance=0.0,
    )

    assert validation.status == "conflicted"
    assert "overlap_value_conflict" in validation.issue_codes


def test_overlap_without_shared_period_is_not_run() -> None:
    module = _module()

    validation = module.validate_overlap(
        (_observation(period="2019"),),
        (_observation(period="2020", provider="world_bank"),),
        absolute_tolerance=0.00001,
        relative_tolerance=0.0,
    )

    assert validation.status == "not_run"
    assert validation.compared_periods == ()
