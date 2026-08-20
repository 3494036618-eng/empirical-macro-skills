from __future__ import annotations

from research_design.contracts import validate_document
from research_design.data_requirements_builder import (
    build_data_requirements,
    resolve_data_requirements,
)


def test_panel_requirements_preserve_scope_and_fail_closed_before_compilation() -> None:
    request: dict[str, object] = {
        "request_id": "rd-request-ffffffffffffffff",
        "variables": [
            {
                "variable_id": "growth",
                "role": "outcome",
                "concept": "实际人均GDP增长",
                "definition_constraints": ["实际值", "人均口径"],
            }
        ],
        "target_population": {"entity_types": ["country"]},
        "unit_of_analysis": "country_time",
        "time_scope": {"start": "2000", "end": "2025", "frequency": "A"},
    }
    estimand: dict[str, object] = {
        "outcome_variable_id": "growth",
        "target_population": "跨国年度面板",
        "horizons": [],
        "status": "specified",
    }

    result = build_data_requirements(request, "panel_association", estimand)

    validate_document("data_requirements", result)
    assert result["status"] == "review_required"
    assert result["unresolved_requirements"] == [
        "macro_data_request_not_compiled",
        "variable_metadata_unresolved",
    ]
    coverage = result["coverage_policy"]
    assert isinstance(coverage, dict)
    assert coverage["scope_may_shrink"] is False
    variables = result["variables"]
    assert isinstance(variables, list)
    assert variables[0]["frequency"] == "A"


def test_dynamic_family_uses_explicit_mapping_but_requires_macro_request(
    valid_request_document: dict[str, object],
) -> None:
    result = build_data_requirements(
        valid_request_document,
        "dynamic_shock_response",
        {"outcome_variable_id": "output_growth"},
    )

    assert result["status"] == "review_required"
    assert "research_use_mapping_unresolved" not in result["unresolved_requirements"]
    assert "macro_data_request_not_compiled" in result["unresolved_requirements"]
    assert result["macro_data_requests"] == []


def test_dynamic_horizon_sets_minimum_required_periods(
    valid_request_document: dict[str, object],
) -> None:
    estimand: dict[str, object] = {
        "status": "specified",
        "horizons": [0, 1, 2, 3, 4],
    }

    result = build_data_requirements(
        valid_request_document,
        "dynamic_shock_response",
        estimand,
    )

    data_structure = result["data_structure"]
    assert isinstance(data_structure, dict)
    assert data_structure["minimum_periods"] == 5


def test_partial_estimand_remains_unresolved_in_data_requirements(
    valid_request_document: dict[str, object],
) -> None:
    result = build_data_requirements(
        valid_request_document,
        "dynamic_shock_response",
        {"status": "partial", "horizons": []},
    )

    assert "estimand_data_scope_unresolved" in result["unresolved_requirements"]


def test_dynamic_response_resolves_through_native_data_contract() -> None:
    """Break caught: dynamic requests require a vendored Schema compatibility copy."""
    research_request: dict[str, object] = {
        "request_id": "rd-request-1234567890abcdef",
        "variables": [
            {
                "variable_id": "inflation",
                "role": "outcome",
                "concept": "美国通胀",
                "definition_constraints": [],
            },
            {
                "variable_id": "shock",
                "role": "shock",
                "concept": "货币政策冲击",
                "definition_constraints": [],
            },
        ],
        "data_entities": [
            {
                "name_or_code": "USA",
                "entity_type": "country",
                "code_scheme": "ISO-3166-1-alpha-3",
            }
        ],
        "target_population": {"entity_types": ["country"]},
        "time_scope": {"start": "1985-Q1", "end": "2007-Q4", "frequency": "Q"},
    }
    estimand: dict[str, object] = {
        "outcome_variable_id": "inflation",
        "treatment_or_shock_variable_id": "shock",
        "target_population": "美国季度时间序列",
        "horizons": list(range(17)),
        "status": "specified",
    }
    macro_request: dict[str, object] = {
        "research_use": "dynamic_response",
        "concepts": [
            {"concept": "美国通胀", "role": "outcome"},
            {"concept": "货币政策冲击", "role": "shock"},
        ],
        "indicators": [
            {"name_or_code": "inflation"},
            {"name_or_code": "shock"},
        ],
        "entities": research_request["data_entities"],
        "time_range": {"start": "1985-Q1", "end": "2007-Q4"},
        "frequency": "Q",
        "unit": "mixed",
        "seasonal_adjustment": "source_native",
        "price_basis": {"type": "index"},
        "currency": None,
        "release_or_vintage": {"mode": "latest"},
    }
    requirements = build_data_requirements(
        research_request,
        "dynamic_shock_response",
        estimand,
    )

    resolved = resolve_data_requirements(
        requirements,
        research_request,
        macro_request,
        {
            "research_use": "dynamic_response",
            "artifact_id": "macro-data-request-" + "1" * 16,
            "artifact_path": "macro-data-requests/request.json",
            "schema_id": "urn:empirical-macro:macro-data:request:0.2.0-beta",
            "checksum_sha256": "1" * 64,
            "validation_status": "validated",
        },
    )

    assert resolved["status"] == "ready_for_macro_data"
    assert resolved["macro_data_requests"][0]["research_use"] == "dynamic_response"
