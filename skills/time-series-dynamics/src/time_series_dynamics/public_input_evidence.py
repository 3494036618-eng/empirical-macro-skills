"""Adapt validated public macro-data output to identified-shock input evidence."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import cast

from time_series_dynamics.input_evidence import materialize_input_evidence

_COMMIT = re.compile(r"^[a-f0-9]{40}$")


def _load(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], document)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _series_codes(result: dict[str, object]) -> list[str]:
    codes: set[str] = set()
    series = result.get("series")
    if not isinstance(series, list):
        raise ValueError("macro-data result has no series")
    for item in series:
        if not isinstance(item, dict):
            raise ValueError("macro-data series must be structured")
        source = item.get("source")
        definition = item.get("indicator_definition")
        if (
            not isinstance(source, dict)
            or source.get("provider") != "public_research_archive"
            or not isinstance(definition, dict)
            or not isinstance(definition.get("code"), str)
        ):
            raise ValueError("macro-data result is not a public research archive")
        codes.add(str(definition["code"]))
    return sorted(codes)


def _validate_ready(result: dict[str, object]) -> None:
    expected = {
        "research_use": "dynamic_response",
        "execution_status": "success",
        "research_readiness": "ready",
        "delivery_eligibility": "analysis_ready",
        "eligible_for_estimation": True,
        "review_required": False,
        "frequency": "Q",
    }
    if any(result.get(field) != value for field, value in expected.items()):
        raise ValueError("macro-data result is not analysis-ready quarterly evidence")
    provenance = result.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("complete") is not True:
        raise ValueError("macro-data provenance is incomplete")


def _source(
    result: dict[str, object],
    public_manifest: dict[str, object],
    data_checksum: str,
) -> tuple[dict[str, object], dict[str, object]]:
    source = public_manifest.get("source")
    raw = public_manifest.get("raw_artifact")
    period = result.get("observation_period")
    if (
        not isinstance(source, dict)
        or not isinstance(raw, dict)
        or not isinstance(period, dict)
    ):
        raise ValueError("public research source metadata is incomplete")
    version = source.get("version")
    license_document = source.get("license")
    if not isinstance(version, str) or _COMMIT.fullmatch(version) is None:
        raise ValueError("public research source version must be a commit")
    if (
        not isinstance(license_document, dict)
        or license_document.get("id") != "CC0-1.0"
        or license_document.get("allows_requested_use") is not True
    ):
        raise ValueError("public research source is not CC0-approved")
    if raw.get("sha256") != data_checksum:
        raise ValueError("public research source checksum mismatch")
    macro_handoff = {
        "schema_version": "0.2.0-beta",
        "result_id": result["result_id"],
        "research_use": "dynamic_response",
        "execution_status": "success",
        "research_readiness": "ready",
        "delivery_eligibility": "analysis_ready",
        "eligible_for_estimation": True,
        "review_required": False,
        "frequency": "Q",
        "observation_period": period,
        "source_checksum": data_checksum,
        "source": {
            "provider": "public_research_archive",
            "dataset": source["title"],
            "version": version,
            "license": "CC0-1.0",
        },
        "variables": _series_codes(result),
        "provenance_complete": True,
        "evidence_kind": "jel_identified_shock",
        "data_profile": "precomputed_columns",
    }
    source_manifest = {
        "schema_version": "0.1.0",
        "source_title": source["title"],
        "source_commit": version,
        "source_url": source["url"],
        "archive_sha256": data_checksum,
        "license": "CC0-1.0",
        "archive_member": raw["path"],
        "member_sha256": data_checksum,
        "sample_start": period["start"],
        "sample_end": period["end"],
    }
    return macro_handoff, source_manifest


def materialize_public_input_evidence(
    *,
    macro_bundle: Path,
    public_manifest_path: Path,
    shock_artifact_path: Path,
    data_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Build standard JEL input evidence from validated macro-data output."""
    result = _load(macro_bundle / "result.json")
    _validate_ready(result)
    public_manifest = _load(public_manifest_path)
    data_checksum = _sha256(data_path)
    macro_handoff, source_manifest = _source(
        result,
        public_manifest,
        data_checksum,
    )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".public-input-adapter-",
        dir=output_dir.parent,
    ) as raw:
        staging = Path(raw)
        macro_path = staging / "macro-data-handoff.json"
        source_path = staging / "source-manifest.json"
        macro_path.write_text(
            json.dumps(macro_handoff, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        source_path.write_text(
            json.dumps(source_manifest, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return materialize_input_evidence(
            macro_handoff_path=macro_path,
            shock_artifact_path=shock_artifact_path,
            source_manifest_path=source_path,
            data_path=data_path,
            output_dir=output_dir,
        )
