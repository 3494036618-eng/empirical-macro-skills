from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest
from jsonschema import ValidationError

from time_series_dynamics.contracts import (
    load_schema,
    validate_document,
    validation_errors,
)
from time_series_dynamics.models import DynamicsRequest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"


def causal_request() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "request_id": "tsd-request-0123456789abcdef",
        "research_plan_ref": "research-plan-0123456789abcdef",
        "macro_data_bundle_refs": ["macro-result-0123456789abcdef"],
        "shock_identification_artifact_ref": "shock-artifact-0123456789abcdef",
        "analysis_track": "identified_shock_irf",
        "estimand_type": "impulse_response",
        "method_profile": "observed_shock_linear_lp",
        "outcome_variable_id": "lcpi",
        "exposure_variable_id": "rr_shock",
        "control_variable_ids": ["dlrgdp", "dlcpi", "dstir"],
        "frequency": "Q",
        "sample_window": {"start": "1985Q1", "end": "2007Q4"},
        "sample_policy": "horizon_specific",
        "horizons": list(range(18)),
        "lags": 4,
        "hac_maxlags": 17,
        "confidence_level": 0.95,
        "claim_eligibility": "causal_candidate",
        "output_unit": "log_points_x100",
    }


def association_request() -> dict[str, object]:
    document = causal_request()
    document.pop("shock_identification_artifact_ref")
    document.update(
        {
            "request_id": "tsd-request-fedcba9876543210",
            "research_plan_ref": "research-plan-fedcba9876543210",
            "analysis_track": "conditional_dynamic_association",
            "estimand_type": "conditional_projection_path",
            "method_profile": "observed_policy_change_projection",
            "exposure_variable_id": "dstir",
            "claim_eligibility": "associational_only",
        }
    )
    return document


def valid_shock_artifact() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "shock_id": "shock-artifact-0123456789abcdef",
        "shock_object_type": "observed_shock",
        "identification_strategy": "narrative",
        "source_title": "Updated Romer-Romer monetary policy shocks",
        "source_version": "JEL-Example5",
        "frequency": "Q",
        "units": "percentage_points",
        "direction": "positive_is_tightening",
        "coverage": {"start": "1985Q1", "end": "2007Q4"},
        "license": {"identifier": "CC0-1.0", "current_use_allowed": True},
        "checksum": "19ca23c02ff86dd1f7c78018e4052eea98de4ecca879f467c3a9d57f55b38d2c",
        "provenance_complete": True,
        "review_status": "approved_for_controlled_estimation",
        "review_required": True,
    }


def valid_result() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "result_id": "tsd-result-0123456789abcdef",
        "request_id": "tsd-request-0123456789abcdef",
        "analysis_track": "identified_shock_irf",
        "estimand_type": "impulse_response",
        "claim_eligibility": "causal_candidate",
        "review_required": True,
        "causal_language_allowed": True,
        "execution_status": "success",
        "interval_scope": "pointwise",
        "horizon_results": [
            {
                "horizon": 0,
                "estimate": 0.03718,
                "standard_error": 0.0641234,
                "confidence_level": 0.95,
                "confidence_lower": -0.0885,
                "confidence_upper": 0.1629,
                "nobs": 88,
                "df_resid": 74.0,
            }
        ],
    }


def test_all_contracts_are_registered_draft_2020_12_schemas() -> None:
    for contract in (
        "research_plan_handoff",
        "macro_data_handoff",
        "shock_artifact",
        "request",
        "result",
        "diagnostics",
        "run_manifest",
    ):
        schema = load_schema(contract)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False


def test_unknown_contract_and_invalid_document_are_reported() -> None:
    with pytest.raises(KeyError, match="unsupported contract"):
        load_schema("unknown")

    document = association_request()
    document["claim_eligibility"] = "causal_candidate"
    errors = validation_errors("request", document)
    assert errors
    assert errors[0]["path"].startswith("/")


def test_causal_and_association_requests_are_valid_and_parseable() -> None:
    for document in (causal_request(), association_request()):
        validate_document("request", document)
        parsed = DynamicsRequest.from_document(document)
        assert parsed.request_id == document["request_id"]
        assert parsed.horizons == tuple(range(18))
        assert parsed.data_profile == "precomputed_columns"
        assert parsed.response_scale == 100.0
        assert parsed.series_bindings == ()


def test_canonical_request_is_valid_and_parseable() -> None:
    document = json.loads(
        (FIXTURES / "canonical-association.request.json").read_text(encoding="utf-8")
    )
    assert isinstance(document, dict)

    validate_document("request", document)
    parsed = DynamicsRequest.from_document(cast(dict[str, object], document))

    assert parsed.data_profile == "canonical_long_table"
    assert parsed.response_scale == 100.0
    assert [binding.variable_id for binding in parsed.series_bindings] == [
        "cpi_log",
        "policy_change",
        "cpi_growth",
        "gdp_growth",
    ]


def test_canonical_request_requires_series_bindings() -> None:
    document = association_request()
    document["data_profile"] = "canonical_long_table"
    document["response_scale"] = 100.0

    with pytest.raises(ValidationError):
        validate_document("request", document)


def test_canonical_request_rejects_duplicate_binding_variable_ids() -> None:
    document = json.loads(
        (FIXTURES / "canonical-association.request.json").read_text(encoding="utf-8")
    )
    duplicate = copy.deepcopy(document["series_bindings"][0])
    duplicate["series_key"] = "DATASET|USA|ALTERNATE_CPI"
    document["series_bindings"].append(duplicate)

    with pytest.raises(ValueError, match="variable IDs must be unique"):
        DynamicsRequest.from_document(cast(dict[str, object], document))


def test_canonical_request_requires_binding_for_every_variable() -> None:
    document = json.loads(
        (FIXTURES / "canonical-association.request.json").read_text(encoding="utf-8")
    )
    document["series_bindings"] = [
        binding for binding in document["series_bindings"] if binding["variable_id"] != "gdp_growth"
    ]

    with pytest.raises(ValueError, match="do not cover"):
        DynamicsRequest.from_document(cast(dict[str, object], document))


def test_runtime_rejects_nonpositive_response_scale() -> None:
    document = association_request()
    document["response_scale"] = 0.0

    with pytest.raises(ValueError, match="response scale must be positive"):
        DynamicsRequest.from_document(document)


def test_causal_request_requires_shock_artifact_reference() -> None:
    document = causal_request()
    document.pop("shock_identification_artifact_ref")

    with pytest.raises(ValidationError):
        validate_document("request", document)


def test_v01_request_accepts_exactly_one_macro_data_bundle() -> None:
    document = association_request()
    document["macro_data_bundle_refs"] = [
        "macro-result-0123456789abcdef",
        "macro-result-fedcba9876543210",
    ]

    with pytest.raises(ValidationError):
        validate_document("request", document)


def test_v01_contracts_reject_unsupported_monthly_frequency() -> None:
    request = association_request()
    request["frequency"] = "M"
    macro = json.loads((FIXTURES / "jel.macro-result.json").read_text(encoding="utf-8"))
    macro["frequency"] = "M"
    shock = valid_shock_artifact()
    shock["frequency"] = "M"

    for contract, document in (
        ("request", request),
        ("macro_data_handoff", macro),
        ("shock_artifact", shock),
    ):
        with pytest.raises(ValidationError):
            validate_document(contract, document)


def test_request_horizons_must_be_contiguous_from_zero() -> None:
    document = association_request()
    document["horizons"] = [0, 2, 1]
    validate_document("request", document)

    with pytest.raises(ValueError, match="contiguous from zero"):
        DynamicsRequest.from_document(document)


def test_association_request_forbids_shock_reference_and_causal_claim() -> None:
    with_shock = association_request()
    with_shock["shock_identification_artifact_ref"] = "shock-artifact-0123456789abcdef"
    with_claim = association_request()
    with_claim["claim_eligibility"] = "causal_candidate"

    for document in (with_shock, with_claim):
        with pytest.raises(ValidationError):
            validate_document("request", document)


def test_result_semantics_cannot_cross_analysis_tracks() -> None:
    association = valid_result()
    association.update(
        {
            "result_id": "tsd-result-fedcba9876543210",
            "request_id": "tsd-request-fedcba9876543210",
            "analysis_track": "conditional_dynamic_association",
            "estimand_type": "conditional_projection_path",
            "claim_eligibility": "associational_only",
            "review_required": False,
            "causal_language_allowed": False,
        }
    )
    validate_document("result", valid_result())
    validate_document("result", association)

    invalid = copy.deepcopy(association)
    invalid["estimand_type"] = "impulse_response"
    with pytest.raises(ValidationError):
        validate_document("result", invalid)


def test_shock_diagnostics_and_manifest_minimal_documents_validate() -> None:
    diagnostics = {
        "schema_version": "0.1.0",
        "request_id": "tsd-request-0123456789abcdef",
        "sample_alignment": {
            "start": "1985Q1",
            "end": "2007Q4",
            "original_nobs": 92,
            "common_nobs": 70,
            "dropped_for_lags": 4,
            "dropped_for_leads": 17,
            "dropped_for_missing": 1,
        },
        "design_matrix": {"columns": 14, "rank": 14},
        "covariance": {"type": "HAC", "kernel": "bartlett", "maxlags": 17},
        "warnings": [],
    }
    manifest = {
        "schema_version": "0.1.0",
        "run_id": "tsd-run-0123456789abcdef0123456789abcdef",
        "request_id": "tsd-request-0123456789abcdef",
        "generated_at": "2026-08-16T00:00:00Z",
        "runtime": {
            "python": "3.12.13",
            "numpy": "2.3.5",
            "pandas": "2.3.3",
            "statsmodels": "0.14.6",
        },
        "input_checksums": {"data": "a" * 64},
        "output_checksums": {"result.json": "b" * 64},
        "secrets_recorded": False,
    }
    validate_document("shock_artifact", valid_shock_artifact())
    validate_document("diagnostics", diagnostics)
    validate_document("run_manifest", manifest)


def test_committed_jel_handoff_fixtures_validate() -> None:
    contracts = {
        "jel.causal.request.json": "request",
        "jel.association.request.json": "request",
        "jel.causal.plan.json": "research_plan_handoff",
        "jel.association.plan.json": "research_plan_handoff",
        "jel.macro-result.json": "macro_data_handoff",
        "jel.shock-artifact.json": "shock_artifact",
    }
    for filename, contract in contracts.items():
        document = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
        validate_document(contract, document)
