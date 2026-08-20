"""把异构上游 bundle 归一化为只读 EvidenceEnvelope。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from research_synthesis.identifiers import (
    canonical_sha256,
    runtime_sanitized_json_bytes,
    sha256_file,
)
from research_synthesis.models import EvidenceEnvelope, ResolvedBundle


def _load(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], document)


def _load_array(path: Path) -> list[dict[str, object]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, list) or any(
        not isinstance(item, dict) for item in document
    ):
        raise ValueError(f"{path.name} must contain a JSON object array")
    return cast(list[dict[str, object]], document)


def _document_sha256(document: dict[str, object]) -> str:
    payload = (
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    return hashlib.sha256(payload).hexdigest()


def _estimator_plan_handoff(plan: dict[str, object]) -> dict[str, object]:
    fields = (
        "schema_version",
        "plan_id",
        "request_id",
        "research_family",
        "intended_claim",
        "primary_design",
        "claim_eligibility",
        "design_readiness",
        "review_required",
    )
    handoff = {field: plan[field] for field in fields}
    handoff["analysis_track"] = _analysis_track(plan)
    return handoff


def _analysis_track(plan: dict[str, object]) -> str:
    track = plan.get("analysis_track")
    if isinstance(track, str):
        return track
    if plan.get("claim_eligibility") == "associational_only":
        return "conditional_dynamic_association"
    raise ValueError("analysis_track_missing")


def _artifacts(
    bundle: ResolvedBundle,
    filenames: tuple[str, ...],
    sanitize_runtime: tuple[str, ...] = (),
) -> tuple[dict[str, object], ...]:
    artifacts: list[dict[str, object]] = []
    for filename in filenames:
        path = bundle.absolute_path / filename
        digest = sha256_file(path)
        if filename in sanitize_runtime:
            value = json.loads(path.read_text(encoding="utf-8"))
            digest = hashlib.sha256(
                runtime_sanitized_json_bytes(value)
            ).hexdigest()
        artifacts.append(
            {
                "path": filename,
                "sha256": f"sha256:{digest}",
            }
        )
    return tuple(artifacts)


def _research_design(bundle: ResolvedBundle) -> EvidenceEnvelope:
    plan = _load(bundle.absolute_path / "research_plan.json")
    request = _load(bundle.absolute_path / "research_request.json")
    audit_path = bundle.absolute_path / "identification_audit.json"
    audit = _load(audit_path) if audit_path.is_file() else None
    manifest = _load(bundle.manifest_path)
    estimand = cast(dict[str, object], plan["estimand"])
    artifact_names = [
        "research_intake.json",
        "research_request.json",
        "research_plan.json",
        "data_requirements.json",
        "research-design-run-manifest.json",
    ]
    if audit is not None:
        artifact_names.insert(3, "identification_audit.json")
    return EvidenceEnvelope(
        artifact_role="research_design",
        skill_name=bundle.reference.skill_name,
        identities={
            "plan_id": str(plan["plan_id"]),
            "request_id": str(request["request_id"]),
            "audit_id": str(audit["audit_id"]) if audit is not None else "",
            "data_requirements_id": str(plan["data_requirements_ref"]),
            "estimand_fingerprint": canonical_sha256(estimand),
            "estimator_handoff_checksum": _document_sha256(
                _estimator_plan_handoff(plan)
            ),
        },
        statuses={
            "execution_status": manifest["execution_status"],
            "design_readiness": plan["design_readiness"],
            "review_required": plan["review_required"],
            "analysis_track": _analysis_track(plan),
            "estimand": estimand,
            "research_question": request["research_question"],
            "primary_design": plan["primary_design"],
            "identification_assumptions": (
                audit["assumptions"] if audit is not None else []
            ),
            "identification_threats": (
                audit["threats"] if audit is not None else []
            ),
        },
        claim_eligibility=str(plan["claim_eligibility"]),
        artifacts=_artifacts(
            bundle,
            tuple(artifact_names),
        ),
        runtime={},
        license_facts=(),
        warnings=tuple(cast(list[str], plan["warnings"])),
    )


def _macro_data(bundle: ResolvedBundle) -> EvidenceEnvelope:
    manifest = _load(bundle.manifest_path)
    macro = _load(bundle.absolute_path / "macro-data-handoff.json")
    shock = _load(
        bundle.absolute_path / "shock-identification-artifact.json"
    )
    source = _load(bundle.absolute_path / "source-manifest.json")
    checksums = cast(dict[str, str], manifest["file_checksums"])
    return EvidenceEnvelope(
        artifact_role="macro_data",
        skill_name=bundle.reference.skill_name,
        identities={
            "evidence_id": str(manifest["evidence_id"]),
            "macro_result_id": str(macro["result_id"]),
            "shock_id": str(shock["shock_id"]),
            "source_commit": str(source["source_commit"]),
            "data_checksum": checksums["aggregatedata_final.dta"],
            "macro_source_checksum": str(macro["source_checksum"]),
            "shock_checksum": str(shock["checksum"]),
            "macro_document_checksum": _document_sha256(macro),
            "shock_document_checksum": _document_sha256(shock),
        },
        statuses={
            "frequency": macro["frequency"],
            "sample_window": macro["observation_period"],
            "delivery_eligibility": macro["delivery_eligibility"],
            "research_use": macro["research_use"],
            "eligible_for_estimation": macro["eligible_for_estimation"],
            "variables": macro["variables"],
            "source": source,
        },
        claim_eligibility="not_eligible",
        artifacts=_artifacts(
            bundle,
            (
                "macro-data-handoff.json",
                "shock-identification-artifact.json",
                "source-manifest.json",
                "aggregatedata_final.dta",
                "input-evidence-manifest.json",
            ),
        ),
        runtime={},
        license_facts=(
            {
                "identifier": str(source["license"]),
                "source_title": str(source["source_title"]),
            },
        ),
        warnings=(),
    )


def _estimator(bundle: ResolvedBundle) -> EvidenceEnvelope:
    request = _load(bundle.absolute_path / "request.json")
    result = _load(bundle.absolute_path / "result.json")
    manifest = _load(bundle.manifest_path)
    inputs = cast(dict[str, str], manifest["input_checksums"])
    macro_refs = cast(list[str], request["macro_data_bundle_refs"])
    return EvidenceEnvelope(
        artifact_role="estimator",
        skill_name=bundle.reference.skill_name,
        identities={
            "request_id": str(request["request_id"]),
            "run_id": str(manifest["run_id"]),
            "result_id": str(result["result_id"]),
            "research_plan_ref": str(request["research_plan_ref"]),
            "macro_result_ref": macro_refs[0],
            "shock_ref": str(request["shock_identification_artifact_ref"]),
            "data_checksum": inputs["data"],
            "macro_handoff_checksum": inputs["macro_data"],
            "shock_artifact_checksum": inputs["shock_artifact"],
            "research_plan_checksum": inputs["research_plan"],
        },
        statuses={
            "analysis_track": request["analysis_track"],
            "estimand_type": request["estimand_type"],
            "claim_eligibility": result["claim_eligibility"],
            "sample_window": request["sample_window"],
            "horizons": request["horizons"],
            "output_unit": request["output_unit"],
            "confidence_level": request["confidence_level"],
            "method_profile": request["method_profile"],
            "outcome_variable_id": request["outcome_variable_id"],
            "exposure_variable_id": request["exposure_variable_id"],
            "horizon_results": result["horizon_results"],
        },
        claim_eligibility=str(result["claim_eligibility"]),
        artifacts=_artifacts(
            bundle,
            (
                "request.json",
                "result.json",
                "diagnostics.json",
                "dynamic-path.csv",
                "dynamic-path.png",
                "run-manifest.json",
            ),
        ),
        runtime=cast(dict[str, str], manifest["runtime"]),
        license_facts=(),
        warnings=tuple(cast(list[str], result.get("warnings", []))),
    )


def _robustness(bundle: ResolvedBundle) -> EvidenceEnvelope:
    request = _load(bundle.absolute_path / "audit-request.json")
    plan = _load(bundle.absolute_path / "audit-plan.json")
    result = _load(bundle.absolute_path / "audit-result.json")
    manifest = _load(bundle.manifest_path)
    checks = _load_array(bundle.absolute_path / "check-results.json")
    return EvidenceEnvelope(
        artifact_role="robustness_audit",
        skill_name=bundle.reference.skill_name,
        identities={
            "audit_request_id": str(request["audit_request_id"]),
            "audit_plan_id": str(plan["audit_plan_id"]),
            "audit_result_id": str(result["audit_result_id"]),
            "run_id": str(manifest["run_id"]),
            "baseline_request_ref": str(result["baseline_request_ref"]),
            "baseline_bundle_ref": str(request["baseline_bundle_ref"]),
        },
        statuses={
            "execution_status": result["execution_status"],
            "audit_readiness": result["audit_readiness"],
            "assessment": result["assessment"],
            "plan_timing": result["plan_timing"],
            "release_recommendation": result["release_recommendation"],
            "required_check_count": result["required_check_count"],
            "completed_required_check_count": result[
                "completed_required_check_count"
            ],
            "check_results": checks,
            "audit_plan": plan,
        },
        claim_eligibility=str(result["claim_eligibility"]),
        artifacts=_artifacts(
            bundle,
            (
                "audit-request.json",
                "audit-plan.json",
                "audit-result.json",
                "check-results.json",
                "comparison-paths.csv",
                "comparison-paths.png",
                "run-manifest.json",
            ),
            sanitize_runtime=("check-results.json",),
        ),
        runtime=cast(dict[str, str], manifest["runtime"]),
        license_facts=(),
        warnings=tuple(cast(list[str], result["warnings"])),
    )


BUILDERS = {
    "research_design": _research_design,
    "macro_data": _macro_data,
    "estimator": _estimator,
    "robustness_audit": _robustness,
}


def build_evidence_envelope(
    role: str,
    bundle: ResolvedBundle,
) -> EvidenceEnvelope:
    """归一化一份已经通过所属 validator 的上游 bundle。"""
    builder = BUILDERS.get(role)
    if builder is None or bundle.reference.artifact_role != role:
        raise ValueError("unsupported_or_mismatched_artifact_role")
    return builder(bundle)
