"""Build data requirements and publish validated macro-data request artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

from research_design.contracts import validate_document

FAMILY_TO_RESEARCH_USE = {
    "descriptive_measurement": "descriptive_latest",
    "panel_association": "panel_analysis",
    "dynamic_shock_response": "dynamic_response",
    "forecasting_nowcasting": "forecasting",
}


def _suffix(document: dict[str, object]) -> str:
    payload = json.dumps(document, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _frequency(request: dict[str, object]) -> str:
    time_scope = request.get("time_scope")
    if isinstance(time_scope, dict):
        frequency = time_scope.get("frequency")
        if frequency in {"D", "W", "M", "Q", "A", "mixed"}:
            return str(frequency)
    return "unknown"


def _entity_scope(request: dict[str, object]) -> list[str]:
    population = request.get("target_population")
    if isinstance(population, dict):
        entity_types = population.get("entity_types")
        if isinstance(entity_types, list):
            values = [str(item) for item in entity_types if isinstance(item, str)]
            if values:
                return values
    return ["unknown"]


def _variable_requirements(request: dict[str, object]) -> list[dict[str, object]]:
    variables = request.get("variables")
    if not isinstance(variables, list):
        return []
    frequency = _frequency(request)
    entity_scope = _entity_scope(request)
    requirements: list[dict[str, object]] = []
    for variable in variables:
        if not isinstance(variable, dict):
            continue
        requirements.append(
            {
                "variable_id": variable.get("variable_id"),
                "role": variable.get("role"),
                "concept": variable.get("concept"),
                "definition_constraints": variable.get("definition_constraints", []),
                "entity_scope": entity_scope,
                "frequency": frequency,
                "unit": None,
                "seasonal_adjustment": "unknown",
                "price_basis": "unknown",
                "currency": None,
                "release_or_vintage": "latest",
                "source_policy": "datapro_first",
            }
        )
    return requirements


def _minimum_periods(estimand: dict[str, object]) -> int:
    horizons = estimand.get("horizons")
    if isinstance(horizons, list):
        valid = [item for item in horizons if isinstance(item, int) and item >= 0]
        if valid:
            return max(valid) + 1
    return 2


def _data_structure(
    request: dict[str, object],
    family: str,
    estimand: dict[str, object],
) -> dict[str, object]:
    if family == "causal_policy_evaluation":
        shape = "event_panel"
    elif family == "panel_association":
        shape = "panel"
    elif family == "forecasting_nowcasting":
        shape = "time_series"
    else:
        shape = "time_series"
    panel = shape in {"panel", "event_panel"}
    return {
        "shape": shape,
        "entity_key": "entity_id" if panel else None,
        "time_key": "period",
        "frequency": _frequency(request),
        "balanced_panel_required": False,
        "minimum_entities": 2 if panel else 1,
        "minimum_periods": _minimum_periods(estimand),
    }


def build_data_requirements(
    request: dict[str, object],
    family: str,
    estimand: dict[str, object],
) -> dict[str, object]:
    unresolved = ["variable_metadata_unresolved"]
    if family in FAMILY_TO_RESEARCH_USE:
        unresolved.append("macro_data_request_not_compiled")
    else:
        unresolved.append("research_use_mapping_unresolved")
    if estimand.get("status") != "specified":
        unresolved.append("estimand_data_scope_unresolved")
    document: dict[str, object] = {
        "schema_version": "0.1.0-draft",
        "requirement_id": f"data-req-{_suffix(request)}",
        "request_id": request.get("request_id"),
        "research_family": family,
        "variables": _variable_requirements(request),
        "data_structure": _data_structure(request, family, estimand),
        "point_in_time_required": family == "forecasting_nowcasting",
        "treatment_timing_required": family == "causal_policy_evaluation",
        "license_requirement": "internal_research",
        "coverage_policy": {
            "scope_may_shrink": False,
            "missingness_must_be_reported": True,
            "selection_rule_pre_registered": True,
        },
        "macro_data_requests": [],
        "status": "review_required",
        "unresolved_requirements": sorted(unresolved),
    }
    validate_document("data_requirements", document)
    return document


def _macro_metadata(document: dict[str, object]) -> dict[str, object]:
    price_basis = document.get("price_basis")
    release = document.get("release_or_vintage")
    entities = document.get("entities")
    entity_scope = []
    if isinstance(entities, list):
        entity_scope = sorted(
            {
                str(entity.get("entity_type"))
                for entity in entities
                if isinstance(entity, dict)
                and isinstance(entity.get("entity_type"), str)
            }
        )
    return {
        "entity_scope": entity_scope or ["unknown"],
        "frequency": document.get("frequency", "unknown"),
        "unit": document.get("unit"),
        "seasonal_adjustment": document.get("seasonal_adjustment", "unknown"),
        "price_basis": (
            price_basis.get("type") if isinstance(price_basis, dict) else "unknown"
        ),
        "currency": document.get("currency"),
        "release_or_vintage": (
            release.get("mode") if isinstance(release, dict) else "latest"
        ),
        "source_policy": "datapro_first",
    }


def _concept_roles(document: dict[str, object]) -> set[tuple[str, str]]:
    concepts = document.get("concepts")
    if not isinstance(concepts, list):
        return set()
    return {
        (concept, role)
        for item in concepts
        if isinstance(item, dict)
        and isinstance((concept := item.get("concept")), str)
        and isinstance((role := item.get("role")), str)
    }


def _required_concept_roles(
    requirements: dict[str, object],
) -> set[tuple[str, str]]:
    variables = requirements.get("variables")
    if not isinstance(variables, list):
        return set()
    role_map = {"forecast_target": "outcome"}
    return {
        (concept, role_map.get(role, role))
        for item in variables
        if isinstance(item, dict)
        and isinstance((concept := item.get("concept")), str)
        and isinstance((role := item.get("role")), str)
    }


def _entity_identities(
    document: dict[str, object],
    field: str,
) -> set[tuple[str, str, str | None]]:
    entities = document.get(field)
    if not isinstance(entities, list):
        return set()
    return {
        (name, entity_type, code_scheme)
        for item in entities
        if isinstance(item, dict)
        and isinstance((name := item.get("name_or_code")), str)
        and isinstance((entity_type := item.get("entity_type")), str)
        and (
            (code_scheme := item.get("code_scheme")) is None
            or isinstance(code_scheme, str)
        )
    }


def _entity_alignment_issues(
    research_request: dict[str, object],
    macro_request: dict[str, object],
) -> list[str]:
    required = _entity_identities(research_request, "data_entities")
    observed = _entity_identities(macro_request, "entities")
    if not required:
        return ["entity_identity_unresolved"]
    return [] if required == observed else ["entity_identity_mismatch"]


def _macro_alignment_issues(
    requirements: dict[str, object],
    research_request: dict[str, object],
    macro_request: dict[str, object],
) -> list[str]:
    issues: list[str] = []
    required_concepts = _required_concept_roles(requirements)
    if not required_concepts <= _concept_roles(macro_request):
        issues.append("concept_role_mismatch")
    indicators = macro_request.get("indicators")
    if not isinstance(indicators, list) or len(indicators) < len(required_concepts):
        issues.append("indicator_coverage_mismatch")
    research_time = research_request.get("time_scope")
    macro_time = macro_request.get("time_range")
    if isinstance(research_time, dict) and isinstance(macro_time, dict):
        for field in ("start", "end"):
            if research_time.get(field) != macro_time.get(field):
                issues.append(f"time_{field}_mismatch")
    data_structure = requirements.get("data_structure")
    if isinstance(data_structure, dict):
        if data_structure.get("frequency") != macro_request.get("frequency"):
            issues.append("frequency_mismatch")
    issues.extend(_entity_alignment_issues(research_request, macro_request))
    return sorted(set(issues))


def resolve_data_requirements(
    requirements: dict[str, object],
    research_request: dict[str, object],
    macro_request: dict[str, object],
    reference: dict[str, str],
) -> dict[str, object]:
    resolved = copy.deepcopy(requirements)
    family = resolved.get("research_family")
    expected_use = FAMILY_TO_RESEARCH_USE.get(str(family))
    if expected_use is None or reference.get("research_use") != expected_use:
        raise ValueError("macro-data research_use is not allowed for research family")
    alignment_issues = _macro_alignment_issues(
        resolved,
        research_request,
        macro_request,
    )
    if alignment_issues:
        raise ValueError(
            "macro-data request does not match research request: "
            + ", ".join(alignment_issues)
        )
    metadata = _macro_metadata(macro_request)
    variables = resolved.get("variables")
    if isinstance(variables, list):
        for variable in variables:
            if isinstance(variable, dict):
                variable.update(metadata)
    resolved["macro_data_requests"] = [reference]
    resolved["status"] = "ready_for_macro_data"
    resolved["unresolved_requirements"] = []
    validate_document("data_requirements", resolved)
    return resolved


def _validated_macro_bytes(
    document: dict[str, object],
    schema_path: Path,
) -> tuple[bytes, str]:
    schema = cast(
        dict[str, object],
        json.loads(schema_path.read_text(encoding="utf-8")),
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (tuple(map(str, error.absolute_path)), error.message),
    )
    if errors:
        path = "/".join(map(str, errors[0].absolute_path)) or "<root>"
        raise ValueError(
            f"macro-data request contract violation at {path}: {errors[0].message}"
        )
    schema_id = schema.get("$id")
    if not isinstance(schema_id, str):
        raise ValueError("macro-data schema is missing $id")
    payload = json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    return payload, schema_id


def write_macro_data_request(
    request_document: dict[str, object],
    output_path: Path,
    macro_schema_path: Path,
) -> dict[str, str]:
    payload, schema_id = _validated_macro_bytes(request_document, macro_schema_path)
    checksum = hashlib.sha256(payload).hexdigest()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    artifact_path = f"{output_path.parent.name}/{output_path.name}"
    return {
        "artifact_id": f"macro-data-request-{checksum[:16]}",
        "artifact_path": artifact_path,
        "schema_id": schema_id,
        "checksum_sha256": checksum,
        "validation_status": "validated",
        "research_use": str(request_document["research_use"]),
    }
