"""Create a stable long table without changing source values."""

from __future__ import annotations

from typing import Any


def item_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("entity_code") or ""),
        str(item.get("indicator_code") or ""),
        str(item.get("time_raw") or ""),
    )


def normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "period": item.get("time_raw"),
        "entity_code": item.get("entity_code"),
        "entity_name": item.get("entity_name"),
        "indicator_code": item.get("indicator_code"),
        "indicator_name": item.get("indicator_name"),
        "value": item.get("value"),
        "source_system": item.get("source_system"),
        "dataset_id": item.get("dataset_id"),
        "dataset_name": item.get("dataset_name"),
        "series_key": item.get("series_key"),
        "frequency": item.get("observed_frequency"),
        "requested_frequency": item.get("requested_frequency"),
        "unit": item["unit"]["value"],
        "unit_status": item["unit"]["status"],
        "seasonal_adjustment": item["seasonal_adjustment"]["value"],
        "seasonal_adjustment_status": item["seasonal_adjustment"]["status"],
        "price_basis": item["price_basis"]["value"],
        "price_basis_status": item["price_basis"]["status"],
        "definition": item["definition"]["value"],
        "definition_status": item["definition"]["status"],
        "release_date": item["release_date"]["value"],
        "release_date_status": item["release_date"]["status"],
        "vintage": item["vintage"]["value"],
        "vintage_status": item["vintage"]["status"],
        "p_date": item["p_date"]["value"],
        "p_date_semantics": item["p_date"]["semantics"],
    }


def normalize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_item(item) for item in sorted(items, key=item_sort_key)]


def build_series_catalog(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item.get("series_key") or ""
        by_key.setdefault(
            key,
            {
                "series_key": item.get("series_key"),
                "provider": item.get("provider", "datapro"),
                "source_system": item.get("source_system"),
                "dataset_id": item.get("dataset_id"),
                "dataset_name": item.get("dataset_name"),
                "entity_code": item.get("entity_code"),
                "entity_name": item.get("entity_name"),
                "indicator_code": item.get("indicator_code"),
                "indicator_name": item.get("indicator_name"),
                "frequency": item.get("observed_frequency"),
                "unit": item["unit"],
                "seasonal_adjustment": item["seasonal_adjustment"],
                "price_basis": item["price_basis"],
                "definition": item["definition"],
                "release_date": item["release_date"],
                "vintage": item["vintage"],
                "p_date": item["p_date"],
            },
        )
    return {"series": [by_key[key] for key in sorted(by_key)]}
