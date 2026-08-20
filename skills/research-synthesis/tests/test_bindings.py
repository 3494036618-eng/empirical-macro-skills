from __future__ import annotations

import copy
from importlib import import_module

import pytest

from research_synthesis.evidence_envelopes import build_evidence_envelope
from research_synthesis.models import EnvelopeMap
from tests.factories import real_resolved_bundles


@pytest.fixture
def envelopes() -> EnvelopeMap:
    return {
        role: build_evidence_envelope(role, bundle)
        for role, bundle in real_resolved_bundles().items()
    }


def test_real_jel_bundles_are_bound(envelopes: EnvelopeMap) -> None:
    module = import_module("research_synthesis.bindings")
    assert hasattr(module, "validate_cross_bundle_binding")

    assert module.validate_cross_bundle_binding(envelopes) == []


@pytest.mark.parametrize(
    ("role", "field", "value", "issue"),
    [
        (
            "estimator",
            "research_plan_ref",
            "research-plan-fedcba9876543210",
            "research_plan_reference_mismatch",
        ),
        (
            "macro_data",
            "data_checksum",
            "0" * 64,
            "data_checksum_mismatch",
        ),
        (
            "robustness_audit",
            "baseline_bundle_ref",
            "tsd-run-fedcba9876543210fedcba9876543210",
            "robustness_baseline_run_mismatch",
        ),
    ],
)
def test_cross_bundle_binding_rejects_identity_drift(
    envelopes: EnvelopeMap,
    role: str,
    field: str,
    value: str,
    issue: str,
) -> None:
    module = import_module("research_synthesis.bindings")
    mutated = copy.deepcopy(envelopes)
    mutated[role].identities[field] = value

    assert issue in module.validate_cross_bundle_binding(mutated)


def test_cross_bundle_binding_rejects_claim_upgrade(
    envelopes: EnvelopeMap,
) -> None:
    module = import_module("research_synthesis.bindings")
    mutated = copy.deepcopy(envelopes)
    mutated["robustness_audit"] = copy.deepcopy(
        mutated["robustness_audit"]
    )
    object.__setattr__(
        mutated["robustness_audit"],
        "claim_eligibility",
        "structural_candidate",
    )

    assert "claim_eligibility_mismatch" in (
        module.validate_cross_bundle_binding(mutated)
    )
