from __future__ import annotations

import copy
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

from robustness_audit.identifiers import canonical_sha256
from robustness_audit.plan_compiler import compile_audit_plan, validate_patch

ROOT = Path(__file__).resolve().parents[1]
TIME_SERIES_ROOT = ROOT.parent / "time-series-dynamics"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resign(document: dict[str, object]) -> None:
    payload = {key: value for key, value in document.items() if key != "checksum"}
    document["checksum"] = f"sha256:{canonical_sha256(payload)}"


def _reidentify_handoff(document: dict[str, object]) -> None:
    payload = {
        key: value
        for key, value in document.items()
        if key not in {"handoff_id", "checksum"}
    }
    document["handoff_id"] = f"rd-robustness-{canonical_sha256(payload)[:32]}"
    _resign(document)


def _documents() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    return (
        _load(ROOT / "fixtures" / "synthetic" / "audit-request.json"),
        _load(ROOT / "fixtures" / "external" / "jel-example5.robustness-handoff.json"),
        _load(
            TIME_SERIES_ROOT / "fixtures" / "synthetic" / "jel.causal.request.json"
        ),
        _load(ROOT / "fixtures" / "synthetic" / "adapter-capability.json"),
    )


def test_compile_plan_does_not_accept_baseline_result() -> None:
    signature = inspect.signature(compile_audit_plan)

    assert tuple(signature.parameters) == (
        "audit_request",
        "handoff",
        "baseline_request",
        "adapter_capability",
    )


def test_compile_plan_materializes_six_stable_derived_alternatives() -> None:
    request, handoff, baseline, capability = _documents()

    plan = compile_audit_plan(request, handoff, baseline, capability)

    assert plan["plan_timing"] == "post_result_exploratory"
    assert plan["baseline_bundle_ref"] == request["baseline_bundle_ref"]
    assert plan["execution_budget"] == {
        "max_variants": 7,
        "max_runtime_seconds": 600,
        "max_parallel_jobs": 1,
    }
    assert len(plan["checks"]) == 5
    assert len(plan["alternatives"]) == 6
    assert [item["patch"] for item in plan["alternatives"]] == [
        {"lags": 3},
        {"lags": 5},
        {"hac_maxlags": 8},
        {"sample_policy": "common_sample"},
        {"sample_window": {"start": "1986Q1", "end": "2007Q4"}},
        {"sample_window": {"start": "1985Q1", "end": "2006Q4"}},
    ]


def test_patch_validation_rejects_estimand_controls_scope_and_bad_values() -> None:
    _, handoff, baseline, capability = _documents()

    assert validate_patch(
        baseline,
        {"outcome_variable_id": "lrgdp"},
        capability,
        handoff,
    ) == ["forbidden_estimand_change"]
    assert validate_patch(
        baseline,
        {"control_variable_ids": ["dlcpi"]},
        capability,
        handoff,
    ) == ["control_patch_not_attested"]
    assert validate_patch(
        baseline,
        {"sample_window": {"start": "1980Q1", "end": "2007Q4"}},
        capability,
        handoff,
    ) == ["sample_window_out_of_coverage"]
    assert validate_patch(
        baseline,
        {"lags": -1},
        capability,
        handoff,
    ) == ["invalid_patch_value"]
    assert validate_patch(
        baseline,
        {"unknown_field": 1},
        capability,
        handoff,
    ) == ["patch_field_not_allowed"]
    assert validate_patch(
        baseline,
        {"sample_window": {"start": "invalid", "end": "2007Q4"}},
        capability,
        handoff,
    ) == ["sample_window_out_of_coverage"]


def test_control_patch_requires_matching_declared_check() -> None:
    _, handoff, baseline, capability = _documents()
    attested = copy.deepcopy(handoff)
    attested["declared_checks"][0]["patches"].append(  # type: ignore[index]
        {"control_variable_ids": ["dlrgdp", "dlcpi", "dstir"]}
    )

    assert validate_patch(
        baseline,
        {"control_variable_ids": ["dlrgdp", "dlcpi", "dstir"]},
        capability,
        attested,
    ) == []
    assert validate_patch(
        baseline,
        {"control_variable_ids": ["different_control"]},
        capability,
        attested,
    ) == ["control_patch_not_attested"]


def test_compile_rejects_stale_handoff_id_claim_upgrade_and_empty_required_check() -> None:
    request, handoff, baseline, capability = _documents()
    stale_id = copy.deepcopy(handoff)
    stale_id["declared_checks"][1]["required"] = False  # type: ignore[index]
    _resign(stale_id)
    with pytest.raises(ValueError, match="robustness_handoff_id_mismatch"):
        compile_audit_plan(request, stale_id, baseline, capability)

    upgraded = copy.deepcopy(handoff)
    upgraded["claim_eligibility"] = "associational_only"
    _reidentify_handoff(upgraded)
    upgraded_request = copy.deepcopy(request)
    upgraded_request["robustness_handoff_ref"] = upgraded["handoff_id"]
    with pytest.raises(ValueError, match="claim_eligibility_mismatch"):
        compile_audit_plan(upgraded_request, upgraded, baseline, capability)

    empty = copy.deepcopy(handoff)
    empty["declared_checks"][1]["patches"] = [{"lags": 4}]  # type: ignore[index]
    _reidentify_handoff(empty)
    empty_request = copy.deepcopy(request)
    empty_request["robustness_handoff_ref"] = empty["handoff_id"]
    with pytest.raises(ValueError, match="required_check_has_no_alternative"):
        compile_audit_plan(empty_request, empty, baseline, capability)

    optional = copy.deepcopy(empty)
    optional["declared_checks"][1]["required"] = False  # type: ignore[index]
    _reidentify_handoff(optional)
    optional_request = copy.deepcopy(request)
    optional_request["robustness_handoff_ref"] = optional["handoff_id"]
    with pytest.raises(ValueError, match="check_has_no_alternative"):
        compile_audit_plan(optional_request, optional, baseline, capability)


def test_compile_rejects_binding_checksum_fingerprint_and_duplicate_errors() -> None:
    request, handoff, baseline, capability = _documents()
    bad_ref = copy.deepcopy(request)
    bad_ref["robustness_handoff_ref"] = "rd-robustness-" + "0" * 32
    bad_checksum = copy.deepcopy(handoff)
    bad_checksum["checksum"] = "sha256:" + "0" * 64
    bad_fingerprint = copy.deepcopy(handoff)
    bad_fingerprint["estimand_fingerprint"] = "sha256:" + "0" * 64
    _reidentify_handoff(bad_fingerprint)
    bad_fingerprint_request = copy.deepcopy(request)
    bad_fingerprint_request["robustness_handoff_ref"] = bad_fingerprint["handoff_id"]
    duplicate = copy.deepcopy(handoff)
    duplicate["declared_checks"][1]["patches"].append({"lags": 3})  # type: ignore[index]
    _reidentify_handoff(duplicate)
    duplicate_request = copy.deepcopy(request)
    duplicate_request["robustness_handoff_ref"] = duplicate["handoff_id"]

    cases = (
        (bad_ref, handoff, "robustness_handoff_reference_mismatch"),
        (request, bad_checksum, "robustness_handoff_checksum_mismatch"),
        (
            bad_fingerprint_request,
            bad_fingerprint,
            "estimand_fingerprint_mismatch",
        ),
        (duplicate_request, duplicate, "duplicate_alternative"),
    )
    for current_request, current_handoff, issue in cases:
        with pytest.raises(ValueError, match=issue):
            compile_audit_plan(
                current_request,
                current_handoff,
                baseline,
                capability,
            )


def test_compile_cli_writes_valid_plan(tmp_path: Path) -> None:
    output = tmp_path / "audit-plan.json"
    run = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/compile_audit_plan.py",
            "--audit-request-json",
            "fixtures/synthetic/audit-request.json",
            "--handoff-json",
            "fixtures/external/jel-example5.robustness-handoff.json",
            "--baseline-request-json",
            str(
                TIME_SERIES_ROOT
                / "fixtures"
                / "synthetic"
                / "jel.causal.request.json"
            ),
            "--adapter-capability-json",
            "fixtures/synthetic/adapter-capability.json",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 0, run.stderr
    assert run.stderr == ""
    document = _load(output)
    assert len(document["alternatives"]) == 6
