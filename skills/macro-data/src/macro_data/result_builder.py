"""Build the versioned macro-data result contract."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from macro_data.models import SeriesIdentity
from macro_data.product_authorization import (
    request_authorization,
    use_authorization_document,
)
from macro_data.provenance import canonical_json


def _series_identity_document(
    first: dict[str, Any],
    provider: str,
) -> dict[str, Any]:
    identity = SeriesIdentity.from_native(
        provider=provider,
        dataset_id=(str(first["dataset_id"]) if first.get("dataset_id") is not None else None),
        series_key=first.get("series_key"),
        entity_code=first.get("entity_code"),
        indicator_code=first.get("indicator_code"),
        frequency=first.get("observed_frequency"),
    )
    complete = all(
        first.get(field) is not None
        for field in (
            "source_system",
            "dataset_id",
            "series_key",
            "entity_code",
            "indicator_code",
            "observed_frequency",
        )
    )
    return {
        "identity_id": identity.identity_id,
        "native_series_id": first.get("series_key"),
        "connector_series_fingerprint": identity.identity_id,
        "identity_status": "verified" if complete else "partial",
        "critical_identity_complete": complete,
    }


def _series_description(
    request: dict[str, Any],
    first: dict[str, Any],
    provider: str,
) -> dict[str, Any]:
    entities = {item["name_or_code"]: item for item in request["entities"]}
    request_entity = entities.get(first.get("entity_code"), {})
    return {
        "indicator_definition": {
            "name": (first.get("indicator_name") or first.get("indicator_code") or "unknown"),
            "code": first.get("indicator_code"),
            "definition": first["definition"]["value"],
            "concept_scheme": None,
        },
        "entity": {
            "name": (first.get("entity_name") or first.get("entity_code") or "unknown"),
            "native_code": first.get("entity_code"),
            "native_scheme": None,
            "canonical_code": first.get("entity_code"),
            "canonical_scheme": request_entity.get("code_scheme"),
            "mapping_version": None,
        },
        "source": {
            "provider": provider,
            "native_source": first.get("source_system"),
            "source_changed_from_preference": (provider not in request["preferred_sources"]),
        },
        "dataset": {
            "id": (str(first["dataset_id"]) if first.get("dataset_id") is not None else None),
            "name": first.get("dataset_name"),
            "version": None,
            "dataflow": first.get("dataset_code"),
        },
    }


def _series_artifacts(
    items: list[dict[str, Any]],
    first: dict[str, Any],
    evaluation: dict[str, Any],
    checksums: dict[str, str],
    provenance_checksum: str,
    retrieved_at: str,
) -> dict[str, Any]:
    periods = sorted(str(item.get("time_raw")) for item in items)
    return {
        "series_id": first.get("series_key"),
        "frequency": first.get("observed_frequency"),
        "unit": first["unit"]["value"],
        "seasonal_adjustment": first["seasonal_adjustment"]["value"],
        "price_basis": first["price_basis"]["value"],
        "currency": first.get("currency"),
        "observation_period": {
            "start": periods[0] if periods else None,
            "end": periods[-1] if periods else None,
        },
        "retrieved_at": retrieved_at,
        "release_date": first["release_date"]["value"],
        "vintage": first["vintage"]["value"],
        "license": first.get("license") or _unknown_license(),
        "raw_artifact": "raw_response.json",
        "normalized_artifact": "data.parquet",
        "transformations": evaluation.get("transformations", []),
        "missingness": {"missing_values": sum(item.get("value") is None for item in items)},
        "checksum": {
            "raw_sha256": checksums["raw_response.json"],
            "normalized_sha256": checksums["data.parquet"],
        },
        "provenance_ref": provenance_checksum,
        "unresolved_conflicts": 0,
        "evidence_references": first.get("evidence_references") or [],
        "warnings": evaluation["issue_codes"],
    }


def _unknown_license() -> dict[str, Any]:
    return {
        "id": None,
        "url": None,
        "attribution": None,
        "use_status": "unknown",
        "allows_requested_use": False,
    }


def _series_documents(
    *,
    request: dict[str, Any],
    evaluation: dict[str, Any],
    checksums: dict[str, str],
    provenance_checksum: str,
    retrieved_at: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in evaluation["selected_items"]:
        grouped[str(item.get("series_key") or "")].append(item)
    documents = []
    for series_key in sorted(grouped):
        items = grouped[series_key]
        first = items[0]
        provider = str(first.get("provider", evaluation.get("provider", "datapro")))
        document = {
            "series_identity": _series_identity_document(first, provider),
            **_series_description(request, first, provider),
            **_series_artifacts(
                items,
                first,
                evaluation,
                checksums,
                provenance_checksum,
                retrieved_at,
            ),
        }
        authorization = use_authorization_document(request, first)
        if authorization is not None:
            document["use_authorization"] = authorization
        documents.append(document)
    return documents


def _dynamic_result_fields(
    request: dict[str, Any],
    evaluation: dict[str, Any],
    checksums: dict[str, str],
) -> dict[str, Any]:
    if request["research_use"] != "dynamic_response":
        return {}
    selected = evaluation["selected_items"]
    periods = sorted(str(item["time_raw"]) for item in selected)
    identity = {
        "request": request,
        "series_keys": sorted({str(item["series_key"]) for item in selected}),
        "source_checksum": checksums["data.csv"],
    }
    digest = hashlib.sha256(canonical_json(identity)).hexdigest()
    return {
        "result_id": "macro-result-" + digest[:32],
        "frequency": request["frequency"],
        "observation_period": {
            "start": periods[0],
            "end": periods[-1],
        },
        "source_checksum": checksums["data.csv"].removeprefix("sha256:"),
    }


def build_result(
    *,
    request: dict[str, Any],
    evaluation: dict[str, Any],
    provenance: dict[str, Any],
    checksums: dict[str, str],
    provenance_checksum: str,
    retrieved_at: str,
    missingness: dict[str, Any],
) -> dict[str, Any]:
    result = {
        "schema_version": "0.2.0-beta",
        "research_use": request["research_use"],
        "request_manifest": {
            "path": "request_manifest.json",
            "sha256": checksums["request_manifest.json"],
        },
        "series": _series_documents(
            request=request,
            evaluation=evaluation,
            checksums=checksums,
            provenance_checksum=provenance_checksum,
            retrieved_at=retrieved_at,
        ),
        "raw_artifacts": [
            {
                "path": "raw_response.json",
                "sha256": checksums["raw_response.json"],
            }
        ],
        "normalized_artifacts": [
            {"path": name, "sha256": checksums[name]}
            for name in (
                "data.csv",
                "data.parquet",
                "quality_report.json",
                "series_catalog.json",
            )
        ],
        "transformations": evaluation.get("transformations", []),
        "missingness": missingness,
        "provenance": provenance,
        "evidence_references": [],
        "execution_status": evaluation["execution_status"],
        "research_readiness": evaluation["research_readiness"],
        "delivery_eligibility": evaluation["delivery_eligibility"],
        "eligible_for_estimation": evaluation["eligible_for_estimation"],
        "source_coverage": evaluation["source_coverage"],
        "warnings": evaluation["issue_codes"],
        "review_required": evaluation["review_required"],
    }
    result.update(_dynamic_result_fields(request, evaluation, checksums))
    authorization = request_authorization(request)
    if authorization is not None:
        result.update(
            {
                "data_use_scope": authorization.data_use_scope,
                "public_payload_policy": authorization.public_payload_policy,
                "product_authorization_ref": authorization.authorization_id,
            }
        )
    return result
