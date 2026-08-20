"""End-to-end declared robustness audit pipeline."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import cast

from robustness_audit.alternative_executor import execute_alternatives
from robustness_audit.assessment import assess_audit
from robustness_audit.baseline_verifier import exact_rerun
from robustness_audit.check_builder import build_check_results
from robustness_audit.contracts import validate_document
from robustness_audit.exporter import (
    build_manifest,
    directory_sha256,
    publish_directory,
    validate_bundle,
    write_comparison_csv,
    write_json,
)
from robustness_audit.identifiers import canonical_sha256, content_id
from robustness_audit.models import AuditPlan
from robustness_audit.plotting import write_comparison_plot
from robustness_audit.reporting import plain_language_summary, technical_summary
from robustness_audit.threat_ledger import build_threat_ledger
from robustness_audit.time_series_adapter import TimeSeriesAdapter


def _load(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _verify_checksum(document: dict[str, object], label: str) -> None:
    expected = document.get("checksum")
    payload = {key: value for key, value in document.items() if key != "checksum"}
    actual = f"sha256:{canonical_sha256(payload)}"
    if expected != actual:
        raise ValueError(f"{label} checksum mismatch")


def _validate_handoff_binding(
    audit_request: dict[str, object],
    audit_plan: dict[str, object],
    handoff: dict[str, object],
) -> None:
    if audit_request["robustness_handoff_ref"] != handoff["handoff_id"]:
        raise ValueError("handoff reference mismatch")
    identity = {
        key: value
        for key, value in handoff.items()
        if key not in {"handoff_id", "checksum"}
    }
    expected_id = f"rd-robustness-{canonical_sha256(identity)[:32]}"
    if handoff["handoff_id"] != expected_id:
        raise ValueError("handoff content ID mismatch")
    bindings = (
        ("analysis_track", "analysis_track"),
        ("claim_eligibility", "claim_eligibility"),
        ("baseline_estimand_fingerprint", "estimand_fingerprint"),
    )
    if any(audit_plan[left] != handoff[right] for left, right in bindings):
        raise ValueError("handoff plan binding mismatch")
    plan_checks = cast(list[dict[str, object]], audit_plan["checks"])
    handoff_checks = cast(list[dict[str, object]], handoff["declared_checks"])
    expected_checks = [
        content_id(
            "ra-check",
            {
                "handoff_id": handoff["handoff_id"],
                "check_family": item["check_family"],
            },
        )
        for item in handoff_checks
    ]
    if [str(item["check_id"]) for item in plan_checks] != expected_checks:
        raise ValueError("handoff check binding mismatch")


def _validate_inputs(
    audit_request: dict[str, object],
    audit_plan: dict[str, object],
    handoff: dict[str, object],
    adapter_capability: dict[str, object],
    baseline_bundle: Path,
) -> None:
    validate_document("audit_request", audit_request)
    validate_document("audit_plan", audit_plan)
    validate_document("adapter_capability", adapter_capability)
    _verify_checksum(audit_plan, "audit plan")
    _verify_checksum(handoff, "handoff")
    _validate_handoff_binding(audit_request, audit_plan, handoff)
    if audit_plan["audit_request_id"] != audit_request["audit_request_id"]:
        raise ValueError("audit request reference mismatch")
    if audit_plan["baseline_request_ref"] != audit_request["baseline_request_ref"]:
        raise ValueError("baseline request reference mismatch")
    if audit_plan["baseline_bundle_ref"] != audit_request["baseline_bundle_ref"]:
        raise ValueError("baseline bundle reference mismatch")
    capability_binding = (
        adapter_capability["adapter_id"],
        adapter_capability["adapter_version"],
    )
    plan_binding = (
        audit_plan["adapter_id"],
        audit_plan["adapter_contract_version"],
    )
    if capability_binding != plan_binding:
        raise ValueError("adapter capability mismatch")
    baseline_manifest = _load(baseline_bundle / "run-manifest.json")
    if baseline_manifest.get("run_id") != audit_request["baseline_bundle_ref"]:
        raise ValueError("baseline bundle run_id mismatch")


def _input_checksums(
    audit_request: dict[str, object],
    audit_plan: dict[str, object],
    handoff: dict[str, object],
    baseline_bundle: Path,
    input_paths: dict[str, Path],
) -> dict[str, str]:
    checksums = {
        "audit_request": canonical_sha256(audit_request),
        "audit_plan": canonical_sha256(audit_plan),
        "robustness_handoff": canonical_sha256(handoff),
        "baseline_bundle": directory_sha256(baseline_bundle),
    }
    checksums.update(
        {
            f"baseline_{name}": hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in input_paths.items()
        }
    )
    return checksums


def _write_staging(
    staging: Path,
    audit_request: dict[str, object],
    audit_plan: dict[str, object],
    audit_result: dict[str, object],
    check_results: list[dict[str, object]],
    comparison_rows: list[dict[str, object]],
    threat_ledger: list[dict[str, object]],
    input_checksums: dict[str, str],
) -> None:
    write_json(staging / "audit-request.json", audit_request)
    write_json(staging / "audit-plan.json", audit_plan)
    write_json(staging / "audit-result.json", audit_result)
    write_json(staging / "check-results.json", check_results)
    write_comparison_csv(staging / "comparison-paths.csv", comparison_rows)
    write_comparison_plot(
        staging / "comparison-paths.png",
        comparison_rows,
        str(audit_plan["plan_timing"]),
    )
    (staging / "technical-summary.md").write_text(
        technical_summary(audit_plan, audit_result, check_results, threat_ledger),
        encoding="utf-8",
    )
    (staging / "plain-language-summary.md").write_text(
        plain_language_summary(audit_result, check_results),
        encoding="utf-8",
    )
    manifest = build_manifest(
        staging,
        str(audit_request["audit_request_id"]),
        str(audit_plan["audit_plan_id"]),
        input_checksums,
    )
    validate_document("run_manifest", manifest)
    write_json(staging / "run-manifest.json", manifest)


def _execute_checks(
    plan: AuditPlan,
    adapter: TimeSeriesAdapter,
    audit_plan: dict[str, object],
    handoff: dict[str, object],
    baseline_bundle: Path,
    input_paths: dict[str, Path],
    staging: Path,
) -> tuple[
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    exact = exact_rerun(
        plan,
        adapter,
        input_paths["request"],
        input_paths,
        baseline_bundle,
        staging / "alternative-bundles" / "exact-rerun",
    )
    records = execute_alternatives(
        plan,
        adapter,
        _load(input_paths["request"]),
        {
            "research_plan": input_paths["research_plan"],
            "macro_result": input_paths["macro_data"],
            "shock_artifact": input_paths["shock_artifact"],
            "data": input_paths["data"],
        },
        staging,
    )
    check_results, comparison_rows = build_check_results(
        audit_plan,
        handoff,
        _load(baseline_bundle / "result.json"),
        exact,
        records,
    )
    threat_ledger = build_threat_ledger(handoff, check_results)
    audit_result = assess_audit(
        audit_plan,
        check_results,
        str(audit_plan["claim_eligibility"]),
    )
    validate_document("audit_result", audit_result)
    return audit_result, check_results, comparison_rows, threat_ledger


def run_robustness_audit(
    audit_request: dict[str, object],
    audit_plan: dict[str, object],
    handoff: dict[str, object],
    baseline_bundle: Path,
    input_paths: dict[str, Path],
    adapter_capability: dict[str, object],
    adapter_root: Path,
    output_dir: Path,
) -> dict[str, object]:
    _validate_inputs(
        audit_request,
        audit_plan,
        handoff,
        adapter_capability,
        baseline_bundle,
    )
    plan = AuditPlan.from_document(audit_plan)
    adapter = TimeSeriesAdapter(adapter_root, adapter_capability)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    (staging / "alternative-bundles").mkdir()
    try:
        audit_result, check_results, comparison_rows, threat_ledger = _execute_checks(
            plan,
            adapter,
            audit_plan,
            handoff,
            baseline_bundle,
            input_paths,
            staging,
        )
        requests = staging / ".requests"
        if requests.exists():
            shutil.rmtree(requests)
        _write_staging(
            staging,
            audit_request,
            audit_plan,
            audit_result,
            check_results,
            comparison_rows,
            threat_ledger,
            _input_checksums(
                audit_request,
                audit_plan,
                handoff,
                baseline_bundle,
                input_paths,
            ),
        )
        validation = validate_bundle(staging)
        if validation["valid"] is not True:
            raise ValueError(f"audit bundle validation failed: {validation['errors']}")
        publish_directory(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {
        "audit_result_id": audit_result["audit_result_id"],
        "assessment": audit_result["assessment"],
        "release_recommendation": audit_result["release_recommendation"],
        "output_dir": str(output_dir),
    }
