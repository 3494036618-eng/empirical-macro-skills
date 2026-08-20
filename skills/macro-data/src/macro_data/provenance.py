"""Build deterministic artifact identifiers and provenance records."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from macro_data import __version__
from macro_data.product_authorization import request_authorization


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_run_id(request: dict[str, Any], raw_response: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    for chunk in encoder.iterencode({"request": request, "raw_response": raw_response}):
        digest.update(chunk.encode("utf-8"))
    return "run-" + digest.hexdigest()[:32]


def build_provenance(
    *,
    request: dict[str, Any],
    raw_response: dict[str, Any],
    input_mode: str,
    provider: str,
    p_date_semantics: str,
    transformations: list[dict[str, Any]],
    artifact_checksums: dict[str, str],
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    run_id = build_run_id(request, raw_response)
    run_digest = run_id.removeprefix("run-")
    document = {
        "schema_version": "0.2.0-beta",
        "run_id": run_id,
        "generated_at": timestamp,
        "input_mode": input_mode,
        "request_artifact": "request_manifest.json",
        "raw_artifacts": ["raw_response.json"],
        "normalized_artifacts": [
            "data.csv",
            "data.parquet",
            "quality_report.json",
            "series_catalog.json",
        ],
        "activities": [
            {
                "activity_id": "activity-" + run_digest[:16],
                "type": "retrieve",
                "agent": "macro-data-connector",
                "started_at": timestamp,
                "ended_at": timestamp,
                "used": ["request_manifest.json"],
                "software": {"name": "macro-data", "version": __version__},
                "generated": ["raw_response.json"],
                "parameters": {
                    "input_mode": input_mode,
                    "provider": provider,
                },
            },
            {
                "activity_id": "activity-" + run_digest[16:32],
                "type": "normalize",
                "agent": "macro-data",
                "started_at": timestamp,
                "ended_at": timestamp,
                "software": {"name": "macro-data", "version": __version__},
                "used": ["raw_response.json"],
                "generated": [
                    "data.csv",
                    "data.parquet",
                    "quality_report.json",
                    "series_catalog.json",
                ],
                "parameters": {
                    "value_transformation": "none",
                    "p_date_semantics": p_date_semantics,
                    "transformations": transformations,
                },
            },
        ],
        "checksums": dict(sorted(artifact_checksums.items())),
        "complete": True,
        "unresolved_links": 0,
    }
    authorization = request_authorization(request)
    if authorization is not None:
        document.update(
            {
                "authorization_ref": authorization.authorization_id,
                "authorization_basis": authorization.authorization_basis,
                "data_use_scope": authorization.data_use_scope,
                "public_payload_policy": authorization.public_payload_policy,
                "credentials_recorded": False,
            }
        )
    return document
