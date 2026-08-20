from __future__ import annotations

import pytest

from robustness_audit.assessment import assess_audit


def _plan(timing: str = "post_result_exploratory") -> dict[str, object]:
    return {
        "audit_plan_id": "ra-plan-0123456789abcdef0123456789abcdef",
        "baseline_request_ref": "tsd-request-0123456789abcdef",
        "plan_timing": timing,
        "checks": [
            {
                "check_id": "ra-check-exact",
                "check_family": "exact_rerun",
                "required": True,
            },
            {
                "check_id": "ra-check-lag",
                "check_family": "lag_sensitivity",
                "required": True,
            },
        ],
    }


def _check(check_id: str, status: str) -> dict[str, object]:
    return {
        "check_result_id": "ra-check-result-" + check_id.removeprefix("ra-check-"),
        "check_id": check_id,
        "status": status,
    }


def test_exact_failure_is_not_assessed_and_stops_ship() -> None:
    result = assess_audit(
        _plan(),
        [
            _check("ra-check-exact", "failed"),
            _check("ra-check-lag", "passed"),
        ],
        "causal_candidate",
    )

    assert result["execution_status"] == "failed"
    assert result["assessment"] == "not_assessed"
    assert result["release_recommendation"] == "stop_ship"


def test_missing_or_error_required_check_is_inconclusive_and_stops_ship() -> None:
    missing = assess_audit(
        _plan(),
        [_check("ra-check-exact", "passed")],
        "causal_candidate",
    )
    errored = assess_audit(
        _plan(),
        [
            _check("ra-check-exact", "passed"),
            _check("ra-check-lag", "error"),
        ],
        "causal_candidate",
    )

    for result in (missing, errored):
        assert result["execution_status"] == "partial"
        assert result["assessment"] == "inconclusive"
        assert result["release_recommendation"] == "stop_ship"


def test_sensitive_and_passed_declared_checks_remain_reviewed_post_result() -> None:
    sensitive = assess_audit(
        _plan(),
        [
            _check("ra-check-exact", "passed"),
            _check("ra-check-lag", "sensitive"),
        ],
        "causal_candidate",
    )
    passed = assess_audit(
        _plan(),
        [
            _check("ra-check-exact", "passed"),
            _check("ra-check-lag", "passed"),
        ],
        "causal_candidate",
    )

    assert sensitive["assessment"] == "sensitive"
    assert sensitive["release_recommendation"] == "review_required"
    assert passed["assessment"] == "passed_declared_checks"
    assert passed["release_recommendation"] == "review_required"
    assert passed["audit_readiness"] == "review_required"


def test_prebound_pass_can_proceed_with_caveats_without_upgrading_claim() -> None:
    result = assess_audit(
        _plan("pre_result_bound"),
        [
            _check("ra-check-exact", "passed"),
            _check("ra-check-lag", "passed"),
        ],
        "associational_only",
    )

    assert result["release_recommendation"] == "proceed_with_caveats"
    assert result["claim_eligibility"] == "associational_only"
    assert result["causal_language_allowed"] is False


def test_duplicate_check_results_are_rejected() -> None:
    duplicate = _check("ra-check-exact", "passed")

    with pytest.raises(ValueError, match="duplicate_check_result"):
        assess_audit(
            _plan(),
            [duplicate, duplicate, _check("ra-check-lag", "passed")],
            "causal_candidate",
        )


def test_optional_sensitive_check_prevents_passed_assessment() -> None:
    plan = _plan("pre_result_bound")
    plan["checks"] = [
        *plan["checks"],  # type: ignore[list-item]
        {
            "check_id": "ra-check-optional",
            "check_family": "optional_sensitivity",
            "required": False,
        },
    ]

    result = assess_audit(
        plan,
        [
            _check("ra-check-exact", "passed"),
            _check("ra-check-lag", "passed"),
            _check("ra-check-optional", "sensitive"),
        ],
        "causal_candidate",
    )

    assert result["assessment"] == "sensitive"
    assert result["release_recommendation"] == "review_required"
