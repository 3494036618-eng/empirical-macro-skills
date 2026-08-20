"""Materialize an approved execution-ready research design bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from research_design import exporter
from research_design.contracts import validate_document

DOCUMENTS = {
    "research_intake": ("research_intake.json", "intake"),
    "research_request": ("research_request.json", "request"),
    "research_plan": ("research_plan.json", "plan"),
    "identification_audit": (
        "identification_audit.json",
        "identification_audit",
    ),
    "data_requirements": ("data_requirements.json", "data_requirements"),
}


def _digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def _selected_candidate_exists(
    intake: dict[str, object],
    request: dict[str, object],
) -> bool:
    selected = request.get("selected_candidate_id")
    candidates = intake.get("candidate_questions")
    return isinstance(candidates, list) and any(
        isinstance(item, dict) and item.get("candidate_id") == selected
        for item in candidates
    )


def _binding_errors(
    intake: dict[str, object],
    request: dict[str, object],
    plan: dict[str, object],
    audit: dict[str, object] | None,
    requirements: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    if request.get("source_intake_id") != intake.get("intake_id"):
        errors.append("intake_request_mismatch")
    if not _selected_candidate_exists(intake, request):
        errors.append("selected_candidate_mismatch")
    if plan.get("request_id") != request.get("request_id"):
        errors.append("plan_request_mismatch")
    if plan.get("intended_claim") != request.get("intended_claim"):
        errors.append("plan_intended_claim_mismatch")
    if requirements.get("request_id") != request.get("request_id"):
        errors.append("data_requirements_request_mismatch")
    if plan.get("data_requirements_ref") != requirements.get("requirement_id"):
        errors.append("plan_data_requirements_mismatch")
    if plan.get("research_family") != requirements.get("research_family"):
        errors.append("research_family_mismatch")
    if plan.get("execution_status") != "success":
        errors.append("plan_execution_failed")
    if plan.get("design_readiness") == "blocked":
        errors.append("plan_design_blocked")
    errors.extend(_estimand_errors(request, plan))
    errors.extend(_audit_errors(plan, audit))
    return errors


def _estimand_errors(
    request: dict[str, object],
    plan: dict[str, object],
) -> list[str]:
    estimand = cast(dict[str, object], plan["estimand"])
    errors: list[str] = []
    horizons = request.get("response_horizons")
    if horizons is not None and horizons != estimand.get("horizons"):
        errors.append("estimand_horizons_mismatch")
    variables = cast(list[dict[str, object]], request["variables"])
    by_role: dict[str, set[str]] = {}
    for variable in variables:
        by_role.setdefault(str(variable["role"]), set()).add(
            str(variable["variable_id"])
        )
    if str(estimand["outcome_variable_id"]) not in by_role.get("outcome", set()):
        errors.append("estimand_outcome_mismatch")
    treatment = estimand.get("treatment_or_shock_variable_id")
    exposure_ids = {
        variable_id
        for role in ("shock", "treatment", "exposure")
        for variable_id in by_role.get(role, set())
    }
    if treatment is not None and str(treatment) not in exposure_ids:
        errors.append("estimand_exposure_mismatch")
    return errors


def _audit_errors(
    plan: dict[str, object],
    audit: dict[str, object] | None,
) -> list[str]:
    reference = plan.get("identification_audit_ref")
    if reference is None:
        return [] if audit is None else ["unexpected_identification_audit"]
    if audit is None:
        return ["identification_audit_required"]
    errors: list[str] = []
    if audit.get("audit_id") != reference:
        errors.append("plan_audit_reference_mismatch")
    if audit.get("request_id") != plan.get("request_id"):
        errors.append("plan_audit_request_mismatch")
    if audit.get("intended_claim") != plan.get("intended_claim"):
        errors.append("plan_audit_intended_claim_mismatch")
    if audit.get("claim_eligibility") != plan.get("claim_eligibility"):
        errors.append("plan_audit_claim_mismatch")
    return errors


def _write_bundle(
    staging: Path,
    documents: dict[str, dict[str, object] | None],
) -> dict[str, object]:
    artifacts: dict[str, object] = {}
    for name, (filename, contract) in DOCUMENTS.items():
        document = documents[name]
        if document is None:
            artifacts[name] = None
            continue
        path = staging / filename
        exporter.write_artifact(path, document, contract)
        artifacts[name] = exporter.artifact_reference(path, contract)
    plan = cast(dict[str, object], documents["research_plan"])
    manifest = {
        "schema_version": "0.1.0-draft",
        "run_id": f"rd-run-{_digest({'plan': plan, 'artifacts': artifacts})}",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifacts": artifacts,
        "execution_status": plan["execution_status"],
        "design_readiness": plan["design_readiness"],
        "claim_eligibility": plan["claim_eligibility"],
        "review_required": plan["review_required"],
        "secrets_recorded": False,
    }
    exporter.write_artifact(
        staging / "research-design-run-manifest.json",
        manifest,
        "run_manifest",
    )
    return manifest


def materialize_execution_ready_bundle(
    intake: dict[str, object],
    request: dict[str, object],
    plan: dict[str, object],
    identification_audit: dict[str, object] | None,
    data_requirements: dict[str, object],
    output_dir: Path,
) -> dict[str, object]:
    """Publish already-approved structured design documents."""
    documents: dict[str, dict[str, object] | None] = {
        "research_intake": intake,
        "research_request": request,
        "research_plan": plan,
        "identification_audit": identification_audit,
        "data_requirements": data_requirements,
    }
    for name, (_, contract) in DOCUMENTS.items():
        document = documents[name]
        if document is not None:
            validate_document(contract, document)
    errors = _binding_errors(
        intake,
        request,
        plan,
        identification_audit,
        data_requirements,
    )
    if errors:
        raise ValueError(",".join(sorted(errors)))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.staging-",
            dir=output_dir.parent,
        )
    )
    try:
        manifest = _write_bundle(staging, documents)
        validation = exporter.validate_bundle(staging)
        if validation["valid"] is not True:
            raise ValueError(f"bundle_validation_failed:{validation['errors']}")
        exporter.publish_directory(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {
        "output_dir": str(output_dir),
        "run_id": manifest["run_id"],
        "plan_id": plan["plan_id"],
        "claim_eligibility": plan["claim_eligibility"],
    }
