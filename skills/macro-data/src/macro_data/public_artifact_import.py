"""Import a checksum-pinned public research archive into a macro-data bundle."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, cast

from macro_data.contracts import validate_document
from macro_data.exporter import export_bundle, validate_bundle
from macro_data.provenance import sha256_file
from macro_data.semantic_validator import evaluate_candidates

_GRAINS = {"M": "month", "Q": "quarter", "A": "year"}


def _load_object(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("public research artifact manifest must be an object")
    return cast(dict[str, Any], document)


def _artifact_path(root: Path, reference: dict[str, Any]) -> Path:
    relative = Path(str(reference["path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("public artifact path must stay inside the manifest directory")
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"public artifact is missing or linked: {relative}")
    return path


def _verify_artifact(path: Path, expected: str, label: str) -> None:
    observed = sha256_file(path).removeprefix("sha256:")
    if observed != expected:
        raise ValueError(f"{label} artifact checksum mismatch")


def _read_rows(
    path: Path,
    period_column: str,
    series: list[dict[str, Any]],
) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {period_column, *(str(item["column"]) for item in series)}
    columns = set(rows[0]) if rows else set()
    missing = sorted(required - columns)
    if missing:
        raise ValueError("public data columns are missing: " + ",".join(missing))
    return rows


def _candidate(
    *,
    row: dict[str, str],
    period_column: str,
    item: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    try:
        value = float(row[str(item["column"])])
    except (TypeError, ValueError) as exc:
        raise ValueError("public data contains a non-numeric value") from exc
    if not math.isfinite(value):
        raise ValueError("public data contains a non-finite value")
    source = cast(dict[str, Any], manifest["source"])
    entity = cast(dict[str, Any], manifest["entity"])
    frequency = str(manifest["frequency"])
    period = str(row[period_column]).replace("-Q", "Q")
    price_basis = item["price_basis"]
    return {
        "provider": "public_research_archive",
        "series_key": item["series_key"],
        "source_system": source["source_system"],
        "dataset_id": source["dataset_id"],
        "dataset_name": source["dataset_name"],
        "dataset_code": source["version"],
        "entity_code": entity["code"],
        "entity_name": entity["name"],
        "indicator_code": item["indicator_code"],
        "indicator_name": item["indicator_name"],
        "time_raw": period,
        "time_grain": _GRAINS[frequency],
        "observed_frequency": frequency,
        "value": value,
        "unit": {
            "value": item["unit"],
            "status": "source_documented" if item["unit"] is not None else "unknown",
        },
        "seasonal_adjustment": {
            "value": item["seasonal_adjustment"],
            "status": (
                "source_documented"
                if item["seasonal_adjustment"] is not None
                else "not_applicable"
            ),
        },
        "price_basis": {
            "value": price_basis,
            "status": "source_documented" if price_basis is not None else "not_applicable",
        },
        "definition": {
            "value": item["definition"],
            "status": "source_provided",
        },
        "release_date": {
            "value": source["source_last_updated"],
            "status": "source_provided",
        },
        "vintage": {
            "value": source["source_last_updated"],
            "status": "source_provided",
        },
        "p_date": {
            "value": source["source_last_updated"],
            "semantics": "source_last_updated",
        },
        "license": source["license"],
        "evidence_references": [source["url"], source["license"]["url"]],
    }


def _evaluation(
    *,
    request: dict[str, Any],
    manifest: dict[str, Any],
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    series = cast(list[dict[str, Any]], manifest["series"])
    period_column = str(cast(dict[str, Any], manifest["data_artifact"])["period_column"])
    candidates = [
        _candidate(
            row=row,
            period_column=period_column,
            item=item,
            manifest=manifest,
        )
        for row in rows
        for item in series
    ]
    parsed = {
        "provider": "public_research_archive",
        "execution": {
            "provider_code": 0,
            "message": "checksum-pinned public research artifact import",
        },
        "candidates": candidates,
        "raw_response": {
            "provider": "public_research_archive",
            "source": manifest["source"],
            "raw_artifact": manifest["raw_artifact"],
            "data_artifact": manifest["data_artifact"],
            "series": manifest["series"],
            "observations": rows,
        },
        "fixture_provenance": {
            "fixture_type": "public-artifact-import",
            "executed_at": manifest["retrieved_at"],
            "request": {"query": request["research_question"]},
        },
        "transformations": [],
    }
    evaluation = evaluate_candidates(request, parsed)
    if evaluation["issue_codes"]:
        evaluation.update(
            {
                "research_readiness": "blocked",
                "delivery_eligibility": "not_deliverable",
                "eligible_for_estimation": False,
                "review_required": True,
            }
        )
        if evaluation["execution_status"] == "success":
            evaluation["execution_status"] = "partial"
    return evaluation


def _publish(staging: Path, output: Path) -> None:
    backup: Path | None = None
    try:
        if output.exists():
            backup = output.with_name(f".{output.name}.backup")
            if backup.exists():
                shutil.rmtree(backup)
            os.replace(output, backup)
        os.replace(staging, output)
    except BaseException:
        if backup is not None and backup.exists() and not output.exists():
            os.replace(backup, output)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup is not None and backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def import_public_artifact_bundle(
    *,
    request: dict[str, Any],
    manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Validate pinned public evidence and publish a standard macro-data bundle."""
    validate_document("request", request)
    manifest = _load_object(manifest_path)
    validate_document("public_research_artifact", manifest)
    license_document = cast(dict[str, Any], cast(dict[str, Any], manifest["source"])["license"])
    if license_document["allows_requested_use"] is not True:
        raise ValueError("source license does not allow requested use")
    root = manifest_path.parent
    raw_reference = cast(dict[str, Any], manifest["raw_artifact"])
    data_reference = cast(dict[str, Any], manifest["data_artifact"])
    raw_path = _artifact_path(root, raw_reference)
    data_path = _artifact_path(root, data_reference)
    _verify_artifact(raw_path, str(raw_reference["sha256"]), "raw")
    _verify_artifact(data_path, str(data_reference["sha256"]), "data")
    rows = _read_rows(
        data_path,
        str(data_reference["period_column"]),
        cast(list[dict[str, Any]], manifest["series"]),
    )
    evaluation = _evaluation(request=request, manifest=manifest, rows=rows)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.staging-",
            dir=output_dir.parent,
        )
    )
    try:
        export_bundle(
            request=request,
            evaluation=evaluation,
            output_dir=staging,
            input_mode="public-artifact-import",
        )
        report = validate_bundle(staging)
        if report["valid"] is not True:
            raise ValueError("imported macro-data bundle validation failed")
        _publish(staging, output_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return evaluation
