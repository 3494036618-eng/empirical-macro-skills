"""串联上游验证、ledgers、单一报告和事务研究包。"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import cast

from jsonschema import ValidationError

from research_synthesis.bindings import validate_cross_bundle_binding
from research_synthesis.bundle_refs import resolve_bundle_ref
from research_synthesis.claim_compiler import compile_claim_ledger
from research_synthesis.contracts import validate_document
from research_synthesis.evidence_envelopes import build_evidence_envelope
from research_synthesis.evidence_index import compile_evidence_index
from research_synthesis.exporter import export_bundle
from research_synthesis.identifiers import scientific_content_id, sha256_file
from research_synthesis.limitations import compile_limitations
from research_synthesis.models import EnvelopeMap, ReportInputs, ResolvedBundle
from research_synthesis.report_builder import build_report, copy_report_assets
from research_synthesis.reproduction import build_reproduction_package
from research_synthesis.reproduction_runner import run_reproduction
from research_synthesis.validator_adapters import validate_upstream_bundle


def _resolve_and_validate(
    request: dict[str, object],
    capabilities: dict[str, object],
    project_root: Path,
) -> tuple[dict[str, ResolvedBundle], EnvelopeMap]:
    refs = cast(list[dict[str, object]], request["bundle_refs"])
    bundles: dict[str, ResolvedBundle] = {}
    envelopes: EnvelopeMap = {}
    for reference in refs:
        role = str(reference["artifact_role"])
        capability = capabilities.get(role)
        if not isinstance(capability, dict):
            raise ValueError(f"adapter_capability_missing:{role}")
        validate_document("adapter_capability", capability)
        bundle = resolve_bundle_ref(reference, project_root)
        evidence = validate_upstream_bundle(bundle, capability)
        if evidence.status != "success":
            issues = ",".join(evidence.issue_codes)
            raise ValueError(f"upstream_validator_failed:{role}:{issues}")
        bundles[role] = bundle
        envelopes[role] = build_evidence_envelope(role, bundle)
    return bundles, envelopes


def _expected_id_errors(
    bundles: dict[str, ResolvedBundle],
    envelopes: EnvelopeMap,
) -> list[str]:
    errors: list[str] = []
    for role, bundle in bundles.items():
        identities = envelopes[role].identities
        for field, expected in bundle.reference.expected_ids.items():
            if identities.get(field) != expected:
                errors.append(f"expected_id_mismatch:{role}:{field}")
    return errors


def _readiness_errors(envelopes: EnvelopeMap) -> list[str]:
    design = envelopes["research_design"].statuses
    errors = []
    if design.get("execution_status") != "success":
        errors.append("research_design_execution_failed")
    if design.get("design_readiness") == "blocked":
        errors.append("research_design_blocked")
    return errors


def _validate_bound_inputs(
    bundles: dict[str, ResolvedBundle],
    envelopes: EnvelopeMap,
) -> None:
    errors = [
        *_expected_id_errors(bundles, envelopes),
        *_readiness_errors(envelopes),
        *validate_cross_bundle_binding(envelopes),
    ]
    if errors:
        raise ValueError(",".join(sorted(errors)))


def _source_roots(project_root: Path) -> dict[str, Path]:
    modules = (
        project_root
        / "30_宏观经济实证Skill"
        / "02_模块开发"
    )
    return {
        "research-design": modules / "research-design",
        "time-series-dynamics": modules / "time-series-dynamics",
        "robustness-audit": modules / "robustness-audit",
        "research-synthesis": modules / "research-synthesis",
    }


def _result_document(
    request: dict[str, object],
    claim_ledger: dict[str, object],
    evidence_index: dict[str, object],
    limitations: dict[str, object],
    reproduction_status: str,
) -> dict[str, object]:
    identity = {
        "request_ref": request["request_id"],
        "claim_ledger_id": claim_ledger["claim_ledger_id"],
        "evidence_index_id": evidence_index["evidence_index_id"],
        "limitations_id": limitations["limitations_id"],
    }
    return {
        "schema_version": "0.1.0",
        "result_id": scientific_content_id("rs-result", identity),
        "request_ref": request["request_id"],
        "execution_status": "success",
        "synthesis_readiness": "review_required",
        "delivery_eligibility": "evidence_only",
        "reproduction_status": reproduction_status,
        "release_recommendation": "stop_ship",
        "effective_claim_eligibility": claim_ledger[
            "effective_claim_eligibility"
        ],
        "primary_output": "research-report.md",
        "warnings": ["M2 数据发布门禁未完成"],
    }


def _reproduction_manifest(
    staging: Path,
    report_inputs: ReportInputs,
    estimator_bundle: Path,
) -> dict[str, object]:
    expected_outputs = {
        relative: f"sha256:{sha256_file(staging / relative)}"
        for relative in (
            "research-report.md",
            "tables/dynamic-path.csv",
            "figures/dynamic-path.png",
        )
    }
    manifest: dict[str, object] = {
        "schema_version": "0.1.0",
        "reproduction_status": "not_run",
        "steps": [
            {
                "step_id": "check-research-outputs",
                "argv": [
                    "python3",
                    "-c",
                    (
                        "from pathlib import Path;"
                        "paths=('research-report.md','tables/dynamic-path.csv',"
                        "'figures/dynamic-path.png');"
                        "raise SystemExit(0 if all(Path(p).is_file() "
                        "for p in paths) else 1)"
                    ),
                ],
                "working_directory": ".",
                "expected_exit_code": 0,
            }
        ],
        "expected_outputs": expected_outputs,
        "runtime": {},
        "network_required": False,
    }
    with tempfile.TemporaryDirectory(
        prefix=".research-synthesis-rerun-",
        dir=staging.parent,
    ) as raw_rerun:
        rerun = Path(raw_rerun)
        (rerun / "research-report.md").write_text(
            build_report(report_inputs),
            encoding="utf-8",
        )
        copy_report_assets(estimator_bundle, rerun)
        evidence = run_reproduction(
            manifest,
            rerun,
            timeout_seconds=60,
        )
    if evidence["status"] != "verified":
        mismatches = cast(list[str], evidence["output_mismatches"])
        raise ValueError(
            "reproduction_failed:" + ",".join(mismatches or ["step_failed"])
        )
    records = cast(list[dict[str, object]], evidence["records"])
    duration = sum(
        cast(float, record["duration_seconds"]) for record in records
    )
    manifest["reproduction_status"] = "verified"
    manifest["runtime"] = {
        "duration_seconds": f"{duration:.6f}",
        "step_count": str(len(records)),
    }
    return manifest


def _failed_result(exc: Exception) -> dict[str, object]:
    return {
        "execution_status": "failed",
        "synthesis_readiness": "blocked",
        "delivery_eligibility": "not_deliverable",
        "reproduction_status": "not_run",
        "release_recommendation": "stop_ship",
        "issue_codes": [str(exc)],
        "output_dir": None,
    }


def run_research_synthesis(
    request: dict[str, object],
    adapter_capabilities: dict[str, object],
    project_root: Path,
    output_dir: Path,
) -> dict[str, object]:
    """运行完整 deterministic research-synthesis pipeline。"""
    staging: Path | None = None
    try:
        validate_document("request", request)
        bundles, envelopes = _resolve_and_validate(
            request,
            adapter_capabilities,
            project_root,
        )
        _validate_bound_inputs(bundles, envelopes)
        evidence = compile_evidence_index(envelopes)
        claims = compile_claim_ledger(envelopes, evidence)
        limitations = compile_limitations(envelopes, claims, evidence)
        report_inputs = ReportInputs(
            request,
            evidence,
            claims,
            limitations,
            envelopes,
        )
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{output_dir.name}.staging-",
                dir=output_dir.parent,
            )
        )
        (staging / "research-report.md").write_text(
            build_report(report_inputs),
            encoding="utf-8",
        )
        copy_report_assets(bundles["estimator"].absolute_path, staging)
        build_reproduction_package(
            staging,
            _source_roots(project_root),
            {role: item.absolute_path for role, item in bundles.items()},
        )
        reproduction_manifest = _reproduction_manifest(
            staging,
            report_inputs,
            bundles["estimator"].absolute_path,
        )
        result = _result_document(
            request,
            claims,
            evidence,
            limitations,
            str(reproduction_manifest["reproduction_status"]),
        )
        documents: dict[str, object] = {
            "request.json": request,
            "result.json": result,
            "claim-ledger.json": claims,
            "evidence-index.json": evidence,
            "limitations.json": limitations,
            "reproduction-manifest.json": reproduction_manifest,
            "references.json": {"sources": request["external_sources"]},
        }
        export_bundle(staging, output_dir, documents)
        staging = None
        return {**result, "output_dir": str(output_dir)}
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        ValidationError,
        json.JSONDecodeError,
    ) as exc:
        return _failed_result(exc)
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
