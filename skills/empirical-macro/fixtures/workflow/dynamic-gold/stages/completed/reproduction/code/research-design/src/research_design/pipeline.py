"""Provider-neutral research-design compilation and transactional export."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from research_design import exporter
from research_design.analysis_tracks import analysis_track_for_design, audit_design
from research_design.data_requirements_builder import (
    build_data_requirements,
    resolve_data_requirements,
    write_macro_data_request,
)
from research_design.design_router import eligible_designs
from research_design.estimand_validator import validate_estimand
from research_design.field_provenance import audit_field_provenance
from research_design.forecasting_gate import forecasting_issues
from research_design.identification_gate import build_identification_audit
from research_design.policy_gate import research_policy_issues
from research_design.readiness import evaluate_readiness
from research_design.request_compiler import compile_request
from research_design.taxonomy import classify_research_family

CLAIM_BY_INTENT = {
    "descriptive": "descriptive_only",
    "associational": "associational_only",
    "predictive": "predictive_only",
    "structural": "structural_candidate",
}

def _digest(*documents: dict[str, object], length: int = 16) -> str:
    payload = json.dumps(documents, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:length]


def _variable_id(request: dict[str, object], roles: set[str]) -> str | None:
    variables = request.get("variables")
    if not isinstance(variables, list):
        return None
    for variable in variables:
        if not isinstance(variable, dict) or variable.get("role") not in roles:
            continue
        variable_id = variable.get("variable_id")
        if isinstance(variable_id, str):
            return variable_id
    return None


def _estimand(request: dict[str, object], family: str) -> dict[str, object]:
    outcome = _variable_id(request, {"outcome", "forecast_target"})
    treatment = _variable_id(request, {"treatment", "shock", "exposure"})
    population = request.get("target_population")
    description = (
        population.get("description") if isinstance(population, dict) else "目标总体待确认"
    )
    forecast = request.get("forecast")
    forecast_horizons = (
        forecast.get("horizons", []) if isinstance(forecast, dict) else []
    )
    response_horizons = request.get("response_horizons")
    horizons = (
        response_horizons
        if isinstance(response_horizons, list)
        else forecast_horizons
    )
    comparison = request.get("comparison")
    types = {
        "descriptive_measurement": "descriptive_statistic",
        "panel_association": "association",
        "dynamic_shock_response": "dynamic_response",
        "causal_policy_evaluation": "att",
        "forecasting_nowcasting": "forecast_target",
        "structural_modeling": "structural_parameter",
    }
    status = "specified"
    dynamic_or_forecast = family in {
        "dynamic_shock_response",
        "forecasting_nowcasting",
    }
    if outcome is None or dynamic_or_forecast and not horizons:
        status = "partial"
    if family in {"dynamic_shock_response", "causal_policy_evaluation"} and treatment is None:
        status = "partial"
    return {
        "type": types.get(family, "unresolved"),
        "outcome_variable_id": outcome,
        "treatment_or_shock_variable_id": treatment,
        "target_population": str(description),
        "comparison": comparison if isinstance(comparison, str) else None,
        "horizons": horizons,
        "status": status,
    }


def _plan_designs(
    request: dict[str, object],
    family: str,
) -> tuple[str, list[dict[str, object]], list[str]]:
    routed = eligible_designs(request, family)
    candidates = [
        {
            "design": item["code"],
            "decision": item["decision"],
            "prerequisites": item["required_diagnostics"],
            "rejection_reasons": item["missing_prerequisites"],
        }
        for item in routed
    ]
    if not candidates:
        candidates = [
            {
                "design": "unresolved",
                "decision": "reject",
                "prerequisites": [],
                "rejection_reasons": ["research_family_undetermined"],
            }
        ]
    adopted = [item["code"] for item in routed if item["decision"] == "adopt"]
    preferred = request.get("preferred_design")
    if isinstance(preferred, str) and preferred in adopted:
        primary = preferred
    else:
        primary = str(adopted[0]) if len(adopted) == 1 else "unresolved"
    diagnostics = sorted(
        {
            str(value)
            for item in routed
            for value in cast_list(item.get("required_diagnostics"))
        }
    )
    return primary, candidates, diagnostics


def cast_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _issue_codes(
    request: dict[str, object],
    family: str,
    estimand: dict[str, object],
    data_requirements: dict[str, object],
) -> set[str]:
    issues = set(audit_field_provenance(request))
    issues.update(validate_estimand({"research_family": family, "estimand": estimand}))
    issues.update(research_policy_issues(request, family))
    if family == "forecasting_nowcasting":
        issues.update(forecasting_issues(request))
    unresolved = data_requirements.get("unresolved_requirements")
    if isinstance(unresolved, list):
        issues.update(str(item) for item in unresolved)
    return issues


def _candidate_family(
    intake: dict[str, object],
    request: dict[str, object],
) -> str | None:
    selected = request.get("selected_candidate_id")
    candidates = intake.get("candidate_questions")
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("candidate_id") != selected:
            continue
        family = candidate.get("research_family_candidate")
        return str(family) if isinstance(family, str) else None
    return None


def _research_family(
    intake: dict[str, object],
    request: dict[str, object],
) -> str:
    classified = classify_research_family(request)
    hinted = _candidate_family(intake, request)
    claim = request.get("intended_claim")
    if hinted == classified:
        return classified
    if hinted == "dynamic_shock_response" and claim in {"causal", "associational"}:
        return hinted
    if hinted == "causal_policy_evaluation" and claim == "causal":
        return hinted
    return classified


def _compile_documents(
    intake: dict[str, object],
    candidate_request: dict[str, object],
    macro_request: dict[str, object] | None = None,
    macro_reference: dict[str, str] | None = None,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object] | None,
    dict[str, object],
]:
    request = compile_request(intake, candidate_request)
    family = _research_family(intake, request)
    estimand = _estimand(request, family)
    primary, candidates, diagnostics = _plan_designs(request, family)
    audit = None
    intended_claim = request.get("intended_claim")
    claim = CLAIM_BY_INTENT.get(str(intended_claim), "not_eligible")
    policy_issues = research_policy_issues(request, family)
    if request.get("intended_claim") in {"causal", "structural"}:
        selected_audit_design = audit_design(primary, candidates)
        audit = build_identification_audit(request, estimand, selected_audit_design)
        claim = str(audit["claim_eligibility"])
        if policy_issues and intended_claim == "causal":
            audit["identification_status"] = "not_identified"
            audit["claim_eligibility"] = "not_eligible"
            claim = "not_eligible"
    requirements = build_data_requirements(request, family, estimand)
    if macro_request is not None and macro_reference is not None:
        requirements = resolve_data_requirements(
            requirements,
            request,
            macro_request,
            macro_reference,
        )
    issues = _issue_codes(request, family, estimand, requirements)
    decisions = {str(item.get("decision")) for item in candidates}
    if decisions <= {"reject"}:
        issues.add("no_eligible_design")
    elif primary == "unresolved":
        issues.add("primary_design_unresolved")
    if family == "forecasting_nowcasting" and (
        forecasting_issues(request) or policy_issues
    ):
        claim = "not_eligible"
    readiness = evaluate_readiness(issues, claim)
    plan = _research_plan(
        request,
        family,
        estimand,
        primary,
        candidates,
        diagnostics,
        audit,
        requirements,
        claim,
        issues,
        readiness,
    )
    return request, plan, audit, requirements


def _research_plan(
    request: dict[str, object],
    family: str,
    estimand: dict[str, object],
    primary: str,
    candidates: list[dict[str, object]],
    diagnostics: list[str],
    audit: dict[str, object] | None,
    requirements: dict[str, object],
    claim: str,
    issues: set[str],
    readiness: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "0.1.0-draft",
        "plan_id": f"research-plan-{_digest(request, estimand)}",
        "request_id": request["request_id"],
        "research_family": family,
        "intended_claim": request["intended_claim"],
        "analysis_track": analysis_track_for_design(primary),
        "estimand": estimand,
        "primary_design": primary,
        "design_candidates": candidates,
        "identification_audit_ref": audit["audit_id"] if audit else None,
        "data_requirements_ref": requirements["requirement_id"],
        "diagnostics": diagnostics,
        "robustness_checks": ["替代口径与样本窗口审查"],
        "reproducibility_requirements": {
            "raw_data_lineage": True,
            "code_and_environment": True,
            "fixed_random_seed": False,
            "artifact_checksums": True,
            "independent_rerun_required": True,
        },
        **readiness,
        "claim_eligibility": claim,
        "warnings": sorted(issues),
    }


def _write_bundle(
    staging: Path,
    intake: dict[str, object],
    request: dict[str, object],
    plan: dict[str, object],
    audit: dict[str, object] | None,
    requirements: dict[str, object],
) -> None:
    artifacts: dict[str, object] = {}
    documents = {
        "research_intake": ("research_intake.json", intake, "intake"),
        "research_request": ("research_request.json", request, "request"),
        "research_plan": ("research_plan.json", plan, "plan"),
        "data_requirements": (
            "data_requirements.json",
            requirements,
            "data_requirements",
        ),
    }
    for name, (filename, document, contract) in documents.items():
        path = staging / filename
        exporter.write_artifact(path, document, contract)
        artifacts[name] = exporter.artifact_reference(path, contract)
    artifacts["identification_audit"] = None
    if audit is not None:
        path = staging / "identification_audit.json"
        exporter.write_artifact(path, audit, "identification_audit")
        artifacts["identification_audit"] = exporter.artifact_reference(
            path,
            "identification_audit",
        )
    manifest = _manifest(plan, artifacts)
    exporter.write_artifact(
        staging / "research-design-run-manifest.json",
        manifest,
        "run_manifest",
    )


def _manifest(
    plan: dict[str, object],
    artifacts: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "0.1.0-draft",
        "run_id": f"rd-run-{_digest(plan, artifacts, length=32)}",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifacts": artifacts,
        "execution_status": plan["execution_status"],
        "design_readiness": plan["design_readiness"],
        "claim_eligibility": plan["claim_eligibility"],
        "review_required": plan["review_required"],
        "secrets_recorded": False,
    }


def run_research_design(
    intake: dict[str, object],
    candidate_request: dict[str, object],
    output_dir: Path,
    macro_schema_path: Path,
    macro_request_document: dict[str, object] | None = None,
) -> dict[str, object]:
    if not macro_schema_path.is_file():
        raise FileNotFoundError(macro_schema_path)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    macro_reference = None
    try:
        if macro_request_document is not None:
            macro_reference = write_macro_data_request(
                macro_request_document,
                staging / "macro-data-requests" / "request.json",
                macro_schema_path,
            )
        request, plan, audit, requirements = _compile_documents(
            intake,
            candidate_request,
            macro_request_document,
            macro_reference,
        )
        _write_bundle(staging, intake, request, plan, audit, requirements)
        validation = exporter.validate_bundle(staging)
        if validation["valid"] is not True:
            raise ValueError(f"bundle validation failed: {validation['errors']}")
        exporter.publish_directory(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    macro_request_path = None
    if macro_reference is not None:
        macro_request_path = str(output_dir / macro_reference["artifact_path"])
    return {
        "output_dir": str(output_dir),
        "design_readiness": plan["design_readiness"],
        "claim_eligibility": plan["claim_eligibility"],
        "issue_codes": plan["warnings"],
        "macro_request_path": macro_request_path,
    }
