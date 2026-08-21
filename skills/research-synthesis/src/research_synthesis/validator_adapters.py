"""把上游 validator CLI 转换为统一验证证据。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

from research_synthesis.contracts import validate_document
from research_synthesis.models import ResolvedBundle, ValidationEvidence
from research_synthesis.subprocess_runner import run_command

MANAGED_PYTHON_PATHS = {".venv/bin/python", ".venv/Scripts/python.exe"}


def _project_root(bundle: ResolvedBundle) -> Path:
    root = bundle.absolute_path
    for _ in bundle.reference.bundle_path.parts:
        root = root.parent
    return root


def _failed(
    evidence: ValidationEvidence,
    issue_code: str,
) -> ValidationEvidence:
    return ValidationEvidence(
        status="failed",
        returncode=evidence.returncode,
        stdout=evidence.stdout,
        stderr=evidence.stderr,
        duration_seconds=evidence.duration_seconds,
        issue_codes=(issue_code,),
    )


def validate_upstream_bundle(
    bundle: ResolvedBundle,
    capability: dict[str, object],
) -> ValidationEvidence:
    """调用与 bundle 身份严格绑定的公共 validator。"""
    validate_document("adapter_capability", capability)
    reference = bundle.reference
    expected = (
        reference.artifact_role,
        reference.skill_name,
        reference.skill_version,
    )
    observed = (
        capability.get("artifact_role"),
        capability.get("skill_name"),
        capability.get("skill_version"),
    )
    if observed != expected:
        raise ValueError("adapter_capability_binding_mismatch")
    argv_template = cast(list[str], capability["validator_argv"])
    argv = [
        str(bundle.absolute_path) if item == "{bundle}" else item
        for item in argv_template
    ]
    cwd = _project_root(bundle) / str(capability["working_directory"])
    if not cwd.is_dir():
        raise ValueError("adapter_working_directory_missing")
    if argv[0] in MANAGED_PYTHON_PATHS and not (cwd / argv[0]).is_file():
        argv[0] = sys.executable
    evidence = run_command(
        argv,
        cwd,
        float(cast(float, capability["timeout_seconds"])),
    )
    if evidence.status != "success":
        return evidence
    try:
        report = json.loads(evidence.stdout)
    except json.JSONDecodeError:
        return _failed(evidence, "validator_output_invalid")
    if not isinstance(report, dict) or not isinstance(report.get("valid"), bool):
        return _failed(evidence, "validator_output_invalid")
    if report["valid"] is not True:
        return _failed(evidence, "upstream_bundle_invalid")
    return evidence
