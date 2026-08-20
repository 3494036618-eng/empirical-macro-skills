from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from robustness_audit.contracts import load_schema, validate_document, validation_errors
from robustness_audit.models import AuditPlan

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"


def adapter_capability() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "adapter_id": "time-series-dynamics",
        "adapter_version": "0.1.0",
        "estimator_contract_version": "0.1.0",
        "supported_analysis_tracks": [
            "identified_shock_irf",
            "conditional_dynamic_association",
        ],
        "supported_patch_fields": [
            "lags",
            "hac_maxlags",
            "sample_policy",
            "sample_window",
            "control_variable_ids",
        ],
        "estimand_fields": [
            "outcome_variable_id",
            "exposure_variable_id",
            "analysis_track",
            "estimand_type",
            "horizons",
        ],
        "unsupported_check_families": [
            "structural_stability_cusum",
            "joint_inference",
        ],
        "max_variants": 32,
        "runtime_requirements": {
            "runner": "uv",
            "run_script": "scripts/run_time_series_dynamics.py",
            "validate_script": "scripts/validate_bundle.py",
        },
    }


def audit_request() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "audit_request_id": "ra-request-0123456789abcdef0123456789abcdef",
        "robustness_handoff_ref": "rd-robustness-0123456789abcdef",
        "baseline_bundle_ref": "tsd-run-0123456789abcdef0123456789abcdef",
        "baseline_request_ref": "tsd-request-0123456789abcdef",
        "adapter_id": "time-series-dynamics",
        "requested_output": "declared_robustness_audit",
    }


def audit_plan() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "audit_plan_id": "ra-plan-0123456789abcdef0123456789abcdef",
        "audit_request_id": "ra-request-0123456789abcdef0123456789abcdef",
        "adapter_id": "time-series-dynamics",
        "adapter_contract_version": "0.1.0",
        "baseline_request_ref": "tsd-request-0123456789abcdef",
        "baseline_bundle_ref": "tsd-run-0123456789abcdef0123456789abcdef",
        "baseline_estimand_fingerprint": "sha256:" + "a" * 64,
        "analysis_track": "identified_shock_irf",
        "claim_eligibility": "causal_candidate",
        "plan_timing": "post_result_exploratory",
        "pre_result_binding": None,
        "checks": [
            {
                "check_id": "ra-check-0123456789abcdef0123456789abcdef",
                "check_family": "exact_rerun",
                "required": True,
                "same_estimand_required": True,
                "anchor_horizons": [0, 4, 8, 12, 17],
                "metrics": ["canonical_result_equality"],
                "decision_rule_ids": ["exact_match_required"],
                "failure_policy": "stop_ship",
                "uses_randomness": False,
            }
        ],
        "alternatives": [
            {
                "alternative_id": "ra-alt-0123456789abcdef0123456789abcdef",
                "check_id": "ra-check-0123456789abcdef0123456789abcdef",
                "patch": {"lags": 3},
            }
        ],
        "decision_rules": [
            {
                "rule_id": "exact_match_required",
                "metric": "canonical_result_equality",
                "operator": "equal",
                "threshold": True,
            }
        ],
        "execution_budget": {
            "max_variants": 7,
            "max_runtime_seconds": 600,
            "max_parallel_jobs": 1,
        },
        "randomness": {"required": False, "seed": None},
        "created_at": "2026-08-16T00:00:00Z",
        "provenance": {"complete": True, "source": "research-design-handoff"},
        "checksum": "sha256:" + "b" * 64,
    }


def audit_result() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "audit_result_id": "ra-result-0123456789abcdef0123456789abcdef",
        "audit_plan_ref": "ra-plan-0123456789abcdef0123456789abcdef",
        "baseline_request_ref": "tsd-request-0123456789abcdef",
        "plan_timing": "post_result_exploratory",
        "execution_status": "success",
        "audit_readiness": "review_required",
        "assessment": "passed_declared_checks",
        "release_recommendation": "review_required",
        "claim_eligibility": "causal_candidate",
        "causal_language_allowed": True,
        "required_check_count": 1,
        "completed_required_check_count": 1,
        "check_result_refs": [
            "ra-check-result-0123456789abcdef0123456789abcdef"
        ],
        "warnings": ["post-result audit is exploratory"],
    }


def test_all_contracts_are_registered_draft_2020_12_schemas() -> None:
    documents = {
        "adapter_capability": adapter_capability(),
        "audit_request": audit_request(),
        "audit_plan": audit_plan(),
        "audit_result": audit_result(),
    }
    for contract in (
        "adapter_capability",
        "audit_request",
        "audit_plan",
        "check_result",
        "audit_result",
        "run_manifest",
    ):
        schema = load_schema(contract)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
    for contract, document in documents.items():
        validate_document(contract, document)


def test_plan_rejects_parallel_prebound_duplicate_or_unseeded_checks() -> None:
    parallel = audit_plan()
    parallel["execution_budget"]["max_parallel_jobs"] = 2  # type: ignore[index]
    prebound = audit_plan()
    prebound["plan_timing"] = "pre_result_bound"
    duplicate = audit_plan()
    duplicate["checks"] = [*duplicate["checks"], copy.deepcopy(duplicate["checks"][0])]  # type: ignore[index]
    random = audit_plan()
    random["checks"][0]["uses_randomness"] = True  # type: ignore[index]
    random["randomness"] = {"required": True, "seed": None}

    for document in (parallel, prebound, duplicate, random):
        with pytest.raises(ValidationError):
            validate_document("audit_plan", document)


def test_plan_rejects_non_exact_check_without_alternative_coverage() -> None:
    document = audit_plan()
    uncovered = copy.deepcopy(document["checks"][0])  # type: ignore[index]
    uncovered["check_id"] = "ra-check-fedcba9876543210fedcba9876543210"
    uncovered["check_family"] = "lag_sensitivity"
    document["checks"] = [*document["checks"], uncovered]  # type: ignore[index]

    with pytest.raises(ValidationError, match="alternative"):
        validate_document("audit_plan", document)


def test_result_state_machine_rejects_invalid_cross_field_states() -> None:
    failed = audit_result()
    failed["execution_status"] = "failed"
    missing = audit_result()
    missing["completed_required_check_count"] = 0
    association = audit_result()
    association["claim_eligibility"] = "associational_only"
    association["causal_language_allowed"] = True

    for document in (failed, missing, association):
        with pytest.raises(ValidationError):
            validate_document("audit_result", document)


def test_validation_errors_and_models_use_stable_paths_and_types() -> None:
    invalid = audit_plan()
    invalid["execution_budget"]["max_variants"] = 33  # type: ignore[index]

    errors = validation_errors("audit_plan", invalid)
    assert errors
    assert errors[0]["path"].startswith("/")

    parsed = AuditPlan.from_document(audit_plan())
    assert parsed.audit_plan_id.startswith("ra-plan-")
    assert parsed.max_variants == 7
    assert parsed.alternatives[0].patch == (("lags", 3),)


def test_committed_contract_fixtures_validate() -> None:
    contracts = {
        "adapter-capability.json": "adapter_capability",
        "audit-request.json": "audit_request",
        "audit-plan.json": "audit_plan",
    }
    for filename, contract in contracts.items():
        document = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
        validate_document(contract, document)
