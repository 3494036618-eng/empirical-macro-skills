from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from research_design.contracts import validate_document
from research_design.robustness_handoff import (
    build_robustness_handoff,
    validate_robustness_handoff,
)

ROOT = Path(__file__).resolve().parents[1]
ROBUSTNESS_ROOT = ROOT.parent / "robustness-audit"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(document: object) -> str:
    payload = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _gold() -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    plan = _load(ROOT / "fixtures" / "gold" / "jel-example5-research-plan.json")
    audit = _load(
        ROOT / "fixtures" / "gold" / "jel-example5-identification-audit.json"
    )
    checks = json.loads(
        (
            ROBUSTNESS_ROOT
            / "fixtures"
            / "external"
            / "jel-example5.audit-checks.json"
        ).read_text(encoding="utf-8")
    )
    return plan, audit, checks


def test_jel_gold_builds_valid_structured_handoff() -> None:
    plan, audit, checks = _gold()
    validate_document("plan", plan)
    validate_document("identification_audit", audit)

    handoff = build_robustness_handoff(plan, audit, checks)

    validate_document("robustness_handoff", handoff)
    validate_robustness_handoff(handoff)
    assert plan["plan_id"] == "research-plan-0123456789abcdef"
    assert plan["identification_audit_ref"] == audit["audit_id"]
    assert handoff["analysis_track"] == "identified_shock_irf"
    assert handoff["claim_eligibility"] == "causal_candidate"
    components = {
        "outcome_variable_id": "lcpi",
        "exposure_variable_id": "rr_shock",
        "analysis_track": "identified_shock_irf",
        "estimand_type": "impulse_response",
        "horizons": list(range(18)),
    }
    expected = hashlib.sha256(
        json.dumps(
            components,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert handoff["estimand_components"] == components
    assert handoff["estimand_fingerprint"] == f"sha256:{expected}"
    assert handoff["review_required"] is True
    assert len(handoff["declared_checks"]) == 5


def test_handoff_rejects_free_text_forbidden_patch_or_missing_causal_audit() -> None:
    plan, audit, checks = _gold()
    free_text: list[object] = ["替代样本窗口"]
    forbidden = copy.deepcopy(checks)
    forbidden[0]["patches"] = [{"outcome_variable_id": "lrgdp"}]

    with pytest.raises(ValueError, match="structured objects"):
        build_robustness_handoff(plan, audit, free_text)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="forbidden patch field"):
        build_robustness_handoff(plan, audit, forbidden)
    with pytest.raises(ValueError, match="identification audit is required"):
        build_robustness_handoff(plan, None, checks)


def test_handoff_checksum_tampering_is_rejected() -> None:
    plan, audit, checks = _gold()
    handoff = build_robustness_handoff(plan, audit, checks)
    handoff["checksum"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_robustness_handoff(handoff)


def test_handoff_content_id_and_identification_audit_binding_are_enforced() -> None:
    plan, audit, checks = _gold()
    handoff = build_robustness_handoff(plan, audit, checks)
    handoff["declared_checks"][0]["required"] = False  # type: ignore[index]
    payload = {key: value for key, value in handoff.items() if key != "checksum"}
    handoff["checksum"] = f"sha256:{_canonical_sha256(payload)}"

    with pytest.raises(ValueError, match="handoff_id mismatch"):
        validate_robustness_handoff(handoff)

    wrong_request = copy.deepcopy(audit)
    wrong_request["request_id"] = "rd-request-fedcba9876543210"
    with pytest.raises(ValueError, match="request mismatch"):
        build_robustness_handoff(plan, wrong_request, checks)

    wrong_reference = copy.deepcopy(audit)
    wrong_reference["audit_id"] = "id-audit-fedcba9876543210"
    with pytest.raises(ValueError, match="reference mismatch"):
        build_robustness_handoff(plan, wrong_reference, checks)

    rejected = copy.deepcopy(audit)
    rejected["identification_status"] = "not_identified"
    rejected["claim_eligibility"] = "not_eligible"
    with pytest.raises(ValueError, match="claim mismatch"):
        build_robustness_handoff(plan, rejected, checks)

    associational = _load(
        ROOT / "fixtures" / "contracts" / "research-plan.valid.json"
    )
    associational["analysis_track"] = "conditional_dynamic_association"
    with pytest.raises(ValueError, match="unexpected identification audit"):
        build_robustness_handoff(associational, audit, checks)

    associational["identification_audit_ref"] = audit["audit_id"]
    associational["request_id"] = audit["request_id"]
    with pytest.raises(ValueError, match="claim mismatch"):
        build_robustness_handoff(associational, audit, checks)


def test_handoff_cli_writes_valid_document(tmp_path: Path) -> None:
    plan, audit, _ = _gold()
    output = tmp_path / "handoff.json"
    run = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/build_robustness_handoff.py",
            "--research-plan-json",
            str(ROOT / "fixtures" / "gold" / "jel-example5-research-plan.json"),
            "--identification-audit-json",
            str(
                ROOT
                / "fixtures"
                / "gold"
                / "jel-example5-identification-audit.json"
            ),
            "--declared-checks-json",
            str(
                ROBUSTNESS_ROOT
                / "fixtures"
                / "external"
                / "jel-example5.audit-checks.json"
            ),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert plan["identification_audit_ref"] == audit["audit_id"]
    assert run.returncode == 0, run.stderr
    assert run.stderr == ""
    document = _load(output)
    validate_document("robustness_handoff", document)
    validate_robustness_handoff(document)
