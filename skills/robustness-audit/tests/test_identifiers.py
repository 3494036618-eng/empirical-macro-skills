from __future__ import annotations

from robustness_audit.identifiers import (
    canonical_sha256,
    content_id,
    estimand_fingerprint,
)


def test_content_ids_are_order_independent_and_content_sensitive() -> None:
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}

    assert content_id("ra-plan", left) == content_id("ra-plan", right)
    assert content_id("ra-plan", left) != content_id("ra-plan", {"a": 1})
    assert len(canonical_sha256(left)) == 64


def test_estimand_fingerprint_reads_only_declared_fields() -> None:
    baseline = {
        "outcome_variable_id": "lcpi",
        "exposure_variable_id": "rr_shock",
        "analysis_track": "identified_shock_irf",
        "lags": 4,
    }
    changed_runtime = {**baseline, "lags": 6}
    changed_estimand = {**baseline, "outcome_variable_id": "lrgdp"}
    fields = (
        "outcome_variable_id",
        "exposure_variable_id",
        "analysis_track",
    )

    assert estimand_fingerprint(baseline, fields) == estimand_fingerprint(
        changed_runtime,
        fields,
    )
    assert estimand_fingerprint(baseline, fields) != estimand_fingerprint(
        changed_estimand,
        fields,
    )
