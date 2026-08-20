from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from research_synthesis.evidence_envelopes import build_evidence_envelope
from research_synthesis.identifiers import sha256_file
from research_synthesis.models import (
    BundleReference,
    EnvelopeMap,
    ResolvedBundle,
)

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
MODULES = PROJECT_ROOT / "30_宏观经济实证Skill" / "02_模块开发"


def _resolved(
    artifact_role: str,
    skill_name: str,
    relative: Path,
    manifest_name: str,
    expected_ids: dict[str, str],
) -> ResolvedBundle:
    absolute = (PROJECT_ROOT / relative).resolve()
    manifest = absolute / manifest_name
    checksum = sha256_file(manifest)
    reference = BundleReference(
        bundle_ref_id=f"rs-bundle-ref-{checksum[:32]}",
        artifact_role=artifact_role,
        skill_name=skill_name,
        skill_version="0.1.0",
        bundle_path=relative,
        manifest_path=Path(manifest_name),
        expected_manifest_sha256=f"sha256:{checksum}",
        expected_ids=expected_ids,
        required=True,
    )
    return ResolvedBundle(reference, absolute, manifest, checksum)


def real_resolved_bundles() -> dict[str, ResolvedBundle]:
    base = Path("30_宏观经济实证Skill") / "02_模块开发"
    return {
        "research_design": _resolved(
            "research_design",
            "research-design",
            base / "research-design" / ".artifacts" / "jel-example5-design",
            "research-design-run-manifest.json",
            {"plan_id": "research-plan-0123456789abcdef"},
        ),
        "macro_data": _resolved(
            "macro_data",
            "time-series-dynamics",
            (
                base
                / "time-series-dynamics"
                / ".artifacts"
                / "jel-example5-input-evidence"
            ),
            "input-evidence-manifest.json",
            {
                "evidence_id": (
                    "tsd-input-evidence-1afbb5cbe867beb4182310bacc1c1a86"
                )
            },
        ),
        "estimator": _resolved(
            "estimator",
            "time-series-dynamics",
            (
                base
                / "time-series-dynamics"
                / ".artifacts"
                / "jel-example5-causal"
            ),
            "run-manifest.json",
            {"request_id": "tsd-request-0123456789abcdef"},
        ),
        "robustness_audit": _resolved(
            "robustness_audit",
            "robustness-audit",
            (
                base
                / "robustness-audit"
                / ".artifacts"
                / "jel-example5-robustness"
            ),
            "run-manifest.json",
            {"audit_result_id": "ra-result-dbaf513e89f215e68f6ecb5609900a5d"},
        ),
    }


def real_envelopes() -> EnvelopeMap:
    return {
        role: build_evidence_envelope(role, bundle)
        for role, bundle in real_resolved_bundles().items()
    }


def _load(path: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )


def real_request() -> dict[str, object]:
    request = _load(ROOT / "fixtures" / "synthetic" / "request.valid.json")
    refs = cast(list[dict[str, object]], request["bundle_refs"])
    bundles = real_resolved_bundles()
    design_plan = _load(
        bundles["research_design"].absolute_path / "research_plan.json"
    )
    data_manifest = _load(bundles["macro_data"].manifest_path)
    estimator_manifest = _load(bundles["estimator"].manifest_path)
    estimator_request = _load(
        bundles["estimator"].absolute_path / "request.json"
    )
    estimator_result = _load(
        bundles["estimator"].absolute_path / "result.json"
    )
    robustness_manifest = _load(bundles["robustness_audit"].manifest_path)
    robustness_result = _load(
        bundles["robustness_audit"].absolute_path / "audit-result.json"
    )
    expected_ids = {
        "research_design": {
            "plan_id": str(design_plan["plan_id"]),
        },
        "macro_data": {
            "evidence_id": str(data_manifest["evidence_id"]),
        },
        "estimator": {
            "request_id": str(estimator_request["request_id"]),
            "run_id": str(estimator_manifest["run_id"]),
            "result_id": str(estimator_result["result_id"]),
        },
        "robustness_audit": {
            "run_id": str(robustness_manifest["run_id"]),
            "audit_result_id": str(
                robustness_result["audit_result_id"]
            ),
        },
    }
    for reference in refs:
        role = str(reference["artifact_role"])
        bundle = bundles[role]
        reference.update(
            {
                "bundle_ref_id": (
                    f"rs-bundle-ref-{bundle.manifest_sha256[:32]}"
                ),
                "bundle_path": bundle.reference.bundle_path.as_posix(),
                "manifest_path": (
                    bundle.reference.manifest_path.as_posix()
                ),
                "expected_manifest_sha256": (
                    f"sha256:{bundle.manifest_sha256}"
                ),
                "expected_ids": expected_ids[role],
                "skill_name": bundle.reference.skill_name,
                "skill_version": bundle.reference.skill_version,
            }
        )
    return request


def local_adapter_capabilities() -> dict[str, object]:
    return _load(ROOT / "configs" / "local-upstream-adapters.json")
