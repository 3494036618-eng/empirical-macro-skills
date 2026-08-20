"""Fail-closed readiness decisions for compiled research plans."""

from __future__ import annotations

HIGH_RISK_ELIGIBILITY = {"causal_candidate", "structural_candidate"}
LOW_RISK_ELIGIBILITY = {
    "descriptive_only",
    "associational_only",
    "predictive_only",
}


def evaluate_readiness(
    issue_codes: set[str],
    claim_eligibility: str,
) -> dict[str, object]:
    if claim_eligibility == "not_eligible":
        return {
            "execution_status": "failed",
            "design_readiness": "blocked",
            "review_required": True,
        }
    if claim_eligibility in HIGH_RISK_ELIGIBILITY:
        return {
            "execution_status": "partial",
            "design_readiness": "review_required",
            "review_required": True,
        }
    if issue_codes or claim_eligibility not in LOW_RISK_ELIGIBILITY:
        return {
            "execution_status": "failed",
            "design_readiness": "blocked",
            "review_required": True,
        }
    return {
        "execution_status": "success",
        "design_readiness": "ready_for_data",
        "review_required": False,
    }
