"""Build a structured research-design handoff for robustness-audit."""

from __future__ import annotations

import hashlib
import json
from typing import cast

from research_design.contracts import validate_document

ALLOWED_PATCH_FIELDS = (
    "control_variable_ids",
    "hac_maxlags",
    "lags",
    "sample_policy",
    "sample_window",
)
FORBIDDEN_PATCH_FIELDS = (
    "analysis_track",
    "claim_eligibility",
    "estimand_type",
    "exposure_variable_id",
    "horizons",
    "macro_data_bundle_refs",
    "outcome_variable_id",
    "output_unit",
    "shock_identification_artifact_ref",
)


def _canonical_sha256(document: object) -> str:
    payload = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _objects(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must contain structured objects")
    return cast(list[dict[str, object]], value)


def _audit_parts(
    audit: dict[str, object] | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], set[str]]:
    if audit is None:
        return [], [], set()
    assumptions = _objects(audit.get("assumptions"), "assumptions")
    threats = _objects(audit.get("threats"), "threats")
    diagnostics = {
        str(item)
        for assumption in assumptions
        for item in cast(list[object], assumption["required_diagnostics"])
    }
    return assumptions, threats, diagnostics


def _validate_checks(
    checks: list[dict[str, object]],
    diagnostics: set[str],
    threat_codes: set[str],
) -> None:
    allowed = set(ALLOWED_PATCH_FIELDS)
    forbidden = set(FORBIDDEN_PATCH_FIELDS)
    for check in checks:
        patches = _objects(check.get("patches"), "patches")
        for patch in patches:
            if fields := forbidden.intersection(patch):
                raise ValueError(f"forbidden patch field: {sorted(fields)[0]}")
            if unknown := set(patch) - allowed:
                raise ValueError(f"unsupported patch field: {sorted(unknown)[0]}")
        threat_refs = {str(item) for item in cast(list[object], check["threat_refs"])}
        diagnostic_refs = {
            str(item) for item in cast(list[object], check["diagnostic_refs"])
        }
        if not threat_refs.issubset(threat_codes):
            raise ValueError("declared check references unknown threat")
        if not diagnostic_refs.issubset(diagnostics):
            raise ValueError("declared check references unknown diagnostic")
        if not threat_refs and not diagnostic_refs:
            raise ValueError("declared check requires a threat or diagnostic mapping")


def _handoff_payload(
    plan: dict[str, object],
    audit: dict[str, object] | None,
    checks: list[dict[str, object]],
) -> dict[str, object]:
    assumptions, threats, audit_diagnostics = _audit_parts(audit)
    plan_diagnostics = {
        str(item) for item in cast(list[object], plan.get("diagnostics", []))
    }
    diagnostics = audit_diagnostics | plan_diagnostics
    threat_codes = {str(item["code"]) for item in threats}
    _validate_checks(checks, diagnostics, threat_codes)
    estimand = cast(dict[str, object], plan["estimand"])
    track = str(plan["analysis_track"])
    components = {
        "outcome_variable_id": estimand["outcome_variable_id"],
        "exposure_variable_id": estimand["treatment_or_shock_variable_id"],
        "analysis_track": track,
        "estimand_type": (
            "impulse_response"
            if track == "identified_shock_irf"
            else "conditional_projection_path"
        ),
        "horizons": estimand["horizons"],
    }
    return {
        "schema_version": "0.1.0-draft",
        "research_plan_ref": plan["plan_id"],
        "identification_audit_ref": audit["audit_id"] if audit else None,
        "estimand_components": components,
        "estimand_fingerprint": "sha256:" + _canonical_sha256(components),
        "analysis_track": plan["analysis_track"],
        "claim_eligibility": plan["claim_eligibility"],
        "assumptions": [
            {
                "code": item["code"],
                "status": item["status"],
                "required_diagnostics": item["required_diagnostics"],
            }
            for item in assumptions
        ],
        "threats": [
            {
                "code": item["code"],
                "severity": item["severity"],
                "status": item["status"],
            }
            for item in threats
        ],
        "required_diagnostics": sorted(diagnostics),
        "declared_checks": checks,
        "allowed_patch_fields": list(ALLOWED_PATCH_FIELDS),
        "forbidden_patch_fields": list(FORBIDDEN_PATCH_FIELDS),
        "review_required": bool(plan["review_required"]),
        "provenance_complete": True,
    }


def build_robustness_handoff(
    research_plan: dict[str, object],
    identification_audit: dict[str, object] | None,
    declared_checks: list[dict[str, object]],
) -> dict[str, object]:
    validate_document("plan", research_plan)
    if identification_audit is not None:
        validate_document("identification_audit", identification_audit)
        if research_plan["identification_audit_ref"] is None:
            raise ValueError("unexpected identification audit")
        if research_plan["identification_audit_ref"] != identification_audit["audit_id"]:
            raise ValueError("identification audit reference mismatch")
        if research_plan["request_id"] != identification_audit["request_id"]:
            raise ValueError("identification audit request mismatch")
        if research_plan["claim_eligibility"] != identification_audit["claim_eligibility"]:
            raise ValueError("identification audit claim mismatch")
    elif research_plan["claim_eligibility"] == "causal_candidate":
        raise ValueError("identification audit is required for causal candidate")
    if research_plan["claim_eligibility"] == "causal_candidate":
        causal_audit = cast(dict[str, object], identification_audit)
        if (
            causal_audit["identification_status"] != "candidate_identified"
            or causal_audit["claim_eligibility"] != "causal_candidate"
        ):
            raise ValueError("identification audit is not eligible for causal candidate")
    checks = _objects(declared_checks, "declared checks")
    document = _handoff_payload(research_plan, identification_audit, checks)
    digest = _canonical_sha256(document)
    document["handoff_id"] = f"rd-robustness-{digest[:32]}"
    document["checksum"] = f"sha256:{_canonical_sha256(document)}"
    validate_document("robustness_handoff", document)
    return document


def validate_robustness_handoff(document: dict[str, object]) -> None:
    validate_document("robustness_handoff", document)
    identity_payload = {
        key: value
        for key, value in document.items()
        if key not in {"handoff_id", "checksum"}
    }
    expected_id = f"rd-robustness-{_canonical_sha256(identity_payload)[:32]}"
    if document["handoff_id"] != expected_id:
        raise ValueError("robustness handoff_id mismatch")
    expected = str(document["checksum"])
    payload = {key: value for key, value in document.items() if key != "checksum"}
    actual = f"sha256:{_canonical_sha256(payload)}"
    if actual != expected:
        raise ValueError("robustness handoff checksum mismatch")
