"""Parse provider responses without inventing missing research semantics."""

from __future__ import annotations

import re
from typing import Any

_UNIT_HINT = re.compile(r"(\d{4}\s*=\s*100)")
_FREQUENCY = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "A"}
_WDI_LICENSE = {
    "id": "CC-BY-4.0",
    "url": "https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators",
    "attribution": "World Bank, World Development Indicators (WDI)",
    "use_status": "allowed",
    "allows_requested_use": True,
}
_WDI_EVIDENCE = [
    "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-world-bank-data-program",
    "https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries",
    "https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators",
]
_DATAPRO_IDENTITY_FIELDS = {
    "series_key",
    "source_system",
    "dataset_id",
    "dataset_name",
    "entity_code",
    "indicator_code",
    "time_raw",
    "time_grain",
    "value",
}
_P_DATE_SEMANTICS = {
    "release_date",
    "source_last_updated",
}


def _metadata(value: Any, *, unresolved: bool = False) -> dict[str, Any]:
    if value is None or value == "":
        return {"value": None, "status": "unresolved" if unresolved else "unknown"}
    return {"value": value, "status": "source_provided"}


def _extract_unit_hint(item: dict[str, Any]) -> str | None:
    text = " ".join(str(item.get(key) or "") for key in ("indicator_name", "series_name"))
    match = _UNIT_HINT.search(text)
    return match.group(1) if match else None


def _p_date_semantics(item: dict[str, Any]) -> str:
    value = item.get("p_date_semantics")
    return str(value) if value in _P_DATE_SEMANTICS else "unresolved"


def _world_bank_unit(metadata: dict[str, Any]) -> dict[str, Any]:
    unit = metadata.get("unit")
    if unit:
        return {"value": unit, "status": "source_provided"}
    text = " ".join(str(metadata.get(key) or "") for key in ("name", "sourceNote"))
    match = _UNIT_HINT.search(text)
    if match:
        return {
            "value": f"index, {match.group(1).replace(' ', '')}",
            "status": "source_documented",
        }
    return {"value": None, "status": "unknown"}


def _world_bank_price_basis(metadata: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(str(metadata.get(key) or "") for key in ("name", "sourceNote"))
    match = _UNIT_HINT.search(text)
    if not match:
        return {"value": None, "status": "unknown"}
    base_period = match.group(1).replace(" ", "")
    return {
        "value": {
            "type": "index",
            "base_period": base_period,
            "chain_linked": None,
        },
        "status": "source_documented",
    }


def _unwrap(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(payload.get("response"), dict):
        fixture = {
            key: payload.get(key)
            for key in ("fixture_type", "executed_at", "completed_at", "request")
            if key in payload
        }
        return payload["response"], fixture
    return payload, {}


def parse_datapro_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a typed candidate representation while preserving native fields."""

    raw, fixture = _unwrap(payload)
    candidates: list[dict[str, Any]] = []
    for native in raw.get("items") or []:
        missing = sorted(_DATAPRO_IDENTITY_FIELDS - set(native))
        if missing:
            raise ValueError("DataPro item missing required fields: " + ", ".join(missing))
        item = native
        grain = str(item.get("time_grain") or "").lower()
        candidates.append(
            {
                **item,
                "provider": "datapro",
                "observed_frequency": _FREQUENCY.get(grain),
                "unit": _metadata(item.get("unit_raw")),
                "seasonal_adjustment": _metadata(item.get("seasonal_adjustment")),
                "price_basis": _metadata(item.get("price_basis")),
                "definition": _metadata(item.get("definition")),
                "release_date": _metadata(item.get("release_date"), unresolved=True),
                "vintage": _metadata(item.get("vintage"), unresolved=True),
                "p_date": {
                    "value": item.get("p_date"),
                    "semantics": _p_date_semantics(item),
                },
                "name_evidence": {"unit_hint": _extract_unit_hint(item)},
            }
        )

    return {
        "provider": "datapro",
        "execution": {
            "provider_code": raw.get("code"),
            "message": raw.get("msg"),
            "dataset_type": raw.get("dataset_type"),
        },
        "candidates": candidates,
        "raw_response": raw,
        "fixture_provenance": fixture,
    }


def _world_bank_page(
    value: Any,
    label: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    page_responses = value.get("page_responses") if isinstance(value, dict) else [value]
    if not isinstance(page_responses, list) or not page_responses:
        raise ValueError(f"World Bank {label} response must contain pages")

    headers: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for page_response in page_responses:
        if (
            not isinstance(page_response, list)
            or len(page_response) != 2
            or not isinstance(page_response[0], dict)
            or not isinstance(page_response[1], list)
            or any(not isinstance(item, dict) for item in page_response[1])
        ):
            raise ValueError(f"World Bank {label} response must contain metadata and rows")
        headers.append(page_response[0])
        rows.extend(page_response[1])

    try:
        expected_pages = int(headers[0].get("pages", 1))
        observed_pages = [int(header.get("page", 1)) for header in headers]
        declared_pages = {int(header.get("pages", 1)) for header in headers}
    except (TypeError, ValueError) as exc:
        raise ValueError(f"World Bank {label} pagination metadata is invalid") from exc
    if (
        len(headers) != expected_pages
        or observed_pages != list(range(1, expected_pages + 1))
        or declared_pages != {expected_pages}
    ):
        raise ValueError(f"World Bank {label} response pagination is incomplete")
    return headers[0], rows


def _world_bank_metadata(
    observation_header: dict[str, Any],
    indicator_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    str,
    Any,
]:
    if not indicator_rows or len(source_rows) != 1:
        raise ValueError("World Bank WDI metadata is incomplete")
    source_metadata = source_rows[0]
    indicator_metadata_by_id = {
        str(item.get("id")): item for item in indicator_rows if item.get("id")
    }
    if (
        str(observation_header.get("sourceid")) != "2"
        or str(source_metadata.get("id")) != "2"
        or source_metadata.get("name") != "World Development Indicators"
        or any(str((item.get("source") or {}).get("id")) != "2" for item in indicator_rows)
    ):
        raise ValueError("World Bank response is not WDI source 2")
    dataset_name = str(source_metadata["name"])
    last_updated = observation_header.get("lastupdated") or source_metadata.get("lastupdated")
    return (
        source_metadata,
        indicator_metadata_by_id,
        dataset_name,
        last_updated,
    )


def _world_bank_candidate(
    observation: dict[str, Any],
    indicator_metadata_by_id: dict[str, dict[str, Any]],
    source_metadata: dict[str, Any],
    dataset_name: str,
    last_updated: Any,
) -> dict[str, Any]:
    indicator = observation.get("indicator") or {}
    country = observation.get("country") or {}
    indicator_code = indicator.get("id")
    entity_code = observation.get("countryiso3code")
    if not indicator_code or not entity_code or not observation.get("date"):
        raise ValueError("World Bank observation identity is incomplete")
    try:
        metadata = indicator_metadata_by_id[str(indicator_code)]
    except KeyError as exc:
        raise ValueError(f"World Bank indicator metadata is missing: {indicator_code}") from exc
    return {
        "provider": "world_bank",
        "series_key": (f"WORLD_BANK|{dataset_name}|{entity_code}|{indicator_code}"),
        "series_name": (f"{country.get('value')} {indicator.get('value')} - {dataset_name}"),
        "source_system": "WORLD_BANK",
        "dataset_id": "2",
        "dataset_name": dataset_name,
        "dataset_code": source_metadata.get("code"),
        "entity_code": entity_code,
        "entity_name": country.get("value"),
        "indicator_code": indicator_code,
        "indicator_name": indicator.get("value"),
        "time_raw": str(observation["date"]),
        "time_grain": "year",
        "year": int(str(observation["date"])[:4]),
        "value": observation.get("value"),
        "obs_status": observation.get("obs_status"),
        "decimal": observation.get("decimal"),
        "footnote": observation.get("footnote"),
        "source_last_updated": last_updated,
        "source_organization": metadata.get("sourceOrganization"),
        "observed_frequency": "A",
        "unit": _world_bank_unit(metadata),
        "seasonal_adjustment": {"value": None, "status": "not_applicable"},
        "price_basis": _world_bank_price_basis(metadata),
        "definition": _metadata(metadata.get("sourceNote")),
        "release_date": _metadata(None, unresolved=True),
        "vintage": _metadata(None, unresolved=True),
        "p_date": {
            "value": last_updated,
            "semantics": "source_last_updated",
        },
        "name_evidence": {
            "unit_hint": _extract_unit_hint({"indicator_name": indicator.get("value")})
        },
        "license": dict(_WDI_LICENSE),
        "evidence_references": list(_WDI_EVIDENCE),
    }


def parse_world_bank_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse a World Bank WDI raw envelope into provider-neutral candidates."""

    observation_header, observations = _world_bank_page(
        payload.get("observations"),
        "observations",
    )
    _, indicator_rows = _world_bank_page(
        payload.get("indicator_metadata"),
        "indicator metadata",
    )
    _, source_rows = _world_bank_page(
        payload.get("source_metadata"),
        "source metadata",
    )
    source_metadata, metadata_by_id, dataset_name, last_updated = _world_bank_metadata(
        observation_header,
        indicator_rows,
        source_rows,
    )
    candidates = [
        _world_bank_candidate(
            observation,
            metadata_by_id,
            source_metadata,
            dataset_name,
            last_updated,
        )
        for observation in observations
    ]
    return {
        "provider": "world_bank",
        "execution": {
            "provider_code": 0,
            "message": "success",
            "dataset_type": "macro",
            "source_id": "2",
            "source_last_updated": last_updated,
        },
        "candidates": candidates,
        "raw_response": payload,
        "fixture_provenance": {},
    }
