from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from research_design.execution_ready_bundle import (
    materialize_execution_ready_bundle,
)
from research_design.exporter import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def _load(path: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )


def _documents() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    plan = _load(FIXTURES / "gold" / "jel-example5-research-plan.json")
    audit = _load(
        FIXTURES / "gold" / "jel-example5-identification-audit.json"
    )
    intake = _load(FIXTURES / "contracts" / "intake.valid.json")
    request = _load(FIXTURES / "contracts" / "request.valid.json")
    requirements = _load(
        FIXTURES / "contracts" / "data-requirements.valid.json"
    )
    intake["intake_id"] = "rd-intake-0123456789abcdef"
    candidates = cast(list[dict[str, object]], intake["candidate_questions"])
    candidates[1]["candidate_id"] = "rd-candidate-01234567"
    intake["recommended_candidate_id"] = "rd-candidate-01234567"
    request.update(
        {
            "source_intake_id": intake["intake_id"],
            "selected_candidate_id": "rd-candidate-01234567",
            "request_id": plan["request_id"],
            "research_question": (
                "一次已识别的意外货币政策收紧如何影响美国季度通胀路径？"
            ),
            "response_horizons": list(range(18)),
            "variables": [
                {
                    "variable_id": "lcpi",
                    "role": "outcome",
                    "concept": "美国季度 CPI 对数水平",
                    "definition_constraints": ["季度"],
                },
                {
                    "variable_id": "rr_shock",
                    "role": "shock",
                    "concept": "已识别货币政策冲击",
                    "definition_constraints": ["不得使用政策利率原始变化"],
                },
            ],
        }
    )
    requirements.update(
        {
            "requirement_id": plan["data_requirements_ref"],
            "request_id": plan["request_id"],
            "research_family": "dynamic_shock_response",
            "macro_data_requests": [],
            "status": "review_required",
        }
    )
    return intake, request, plan, audit, requirements


def test_execution_ready_public_surface_exists() -> None:
    assert importlib.util.find_spec("research_design.execution_ready_bundle") is not None
    assert (ROOT / "scripts" / "materialize_execution_ready_bundle.py").is_file()
    assert (ROOT / "scripts" / "validate_bundle.py").is_file()


def test_execution_ready_materializer_is_public() -> None:
    spec = importlib.util.find_spec("research_design.execution_ready_bundle")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "materialize_execution_ready_bundle")


def test_execution_ready_bundle_preserves_approved_identity(
    tmp_path: Path,
) -> None:
    intake, request, plan, audit, requirements = _documents()
    output = tmp_path / "bundle"

    result = materialize_execution_ready_bundle(
        intake,
        request,
        plan,
        audit,
        requirements,
        output,
    )

    assert result["plan_id"] == "research-plan-0123456789abcdef"
    assert validate_bundle(output) == {"valid": True, "errors": []}


def test_execution_ready_bundle_rejects_cross_document_mismatch(
    tmp_path: Path,
) -> None:
    intake, request, plan, audit, requirements = _documents()
    audit["audit_id"] = "id-audit-fedcba9876543210"

    with pytest.raises(ValueError, match="plan_audit_reference_mismatch"):
        materialize_execution_ready_bundle(
            intake,
            request,
            plan,
            audit,
            requirements,
            tmp_path / "bundle",
        )


@pytest.mark.parametrize(
    ("target", "field", "value", "issue"),
    [
        (
            "request",
            "source_intake_id",
            "rd-intake-fedcba9876543210",
            "intake_request_mismatch",
        ),
        (
            "request",
            "selected_candidate_id",
            "rd-candidate-fedcba98",
            "selected_candidate_mismatch",
        ),
        (
            "plan",
            "request_id",
            "rd-request-fedcba9876543210",
            "plan_request_mismatch",
        ),
        (
            "requirements",
            "request_id",
            "rd-request-fedcba9876543210",
            "data_requirements_request_mismatch",
        ),
        (
            "requirements",
            "requirement_id",
            "data-req-fedcba9876543210",
            "plan_data_requirements_mismatch",
        ),
        (
            "audit",
            "request_id",
            "rd-request-fedcba9876543210",
            "plan_audit_request_mismatch",
        ),
    ],
)
def test_execution_ready_bundle_rejects_identity_mismatches(
    tmp_path: Path,
    target: str,
    field: str,
    value: str,
    issue: str,
) -> None:
    intake, request, plan, audit, requirements = _documents()
    documents = {
        "intake": intake,
        "request": request,
        "plan": plan,
        "audit": audit,
        "requirements": requirements,
    }
    documents[target][field] = value

    with pytest.raises(ValueError, match=issue):
        materialize_execution_ready_bundle(
            intake,
            request,
            plan,
            audit,
            requirements,
            tmp_path / "bundle",
        )


def test_execution_ready_bundle_requires_causal_audit(tmp_path: Path) -> None:
    intake, request, plan, _, requirements = _documents()

    with pytest.raises(ValueError, match="identification_audit_required"):
        materialize_execution_ready_bundle(
            intake,
            request,
            plan,
            None,
            requirements,
            tmp_path / "bundle",
        )


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("execution_status", "failed", "plan_execution_failed"),
        ("design_readiness", "blocked", "plan_design_blocked"),
    ],
)
def test_execution_ready_bundle_rejects_failed_or_blocked_plan(
    tmp_path: Path,
    field: str,
    value: str,
    issue: str,
) -> None:
    intake, request, plan, audit, requirements = _documents()
    plan[field] = value

    with pytest.raises(ValueError, match=issue):
        materialize_execution_ready_bundle(
            intake,
            request,
            plan,
            audit,
            requirements,
            tmp_path / "bundle",
        )


@pytest.mark.parametrize(
    ("mutation", "issue"),
    [
        ("horizons", "estimand_horizons_mismatch"),
        ("outcome", "estimand_outcome_mismatch"),
        ("research_family", "research_family_mismatch"),
    ],
)
def test_execution_ready_bundle_rejects_estimand_drift(
    tmp_path: Path,
    mutation: str,
    issue: str,
) -> None:
    intake, request, plan, audit, requirements = _documents()
    if mutation == "horizons":
        request["response_horizons"] = list(range(17))
    elif mutation == "outcome":
        variables = cast(list[dict[str, object]], request["variables"])
        variables[0]["variable_id"] = "wrong_outcome"
    else:
        requirements["research_family"] = "panel_association"

    with pytest.raises(ValueError, match=issue):
        materialize_execution_ready_bundle(
            intake,
            request,
            plan,
            audit,
            requirements,
            tmp_path / "bundle",
        )


def test_execution_ready_bundle_can_replace_previous_output(tmp_path: Path) -> None:
    intake, request, plan, audit, requirements = _documents()
    output = tmp_path / "bundle"

    first = materialize_execution_ready_bundle(
        intake, request, plan, audit, requirements, output
    )
    second = materialize_execution_ready_bundle(
        intake, request, plan, audit, requirements, output
    )

    assert first["run_id"] == second["run_id"]
    assert validate_bundle(output)["valid"] is True


def test_validate_bundle_cli_returns_structured_failure(tmp_path: Path) -> None:
    run = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/validate_bundle.py",
            str(tmp_path / "missing"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 1
    assert json.loads(run.stdout)["valid"] is False


def test_materialize_cli_writes_valid_bundle(tmp_path: Path) -> None:
    intake, request, plan, audit, requirements = _documents()
    paths = {}
    for name, document in (
        ("intake", intake),
        ("request", request),
        ("plan", plan),
        ("audit", audit),
        ("requirements", requirements),
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths[name] = path
    output = tmp_path / "bundle"

    run = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/materialize_execution_ready_bundle.py",
            "--intake-json",
            str(paths["intake"]),
            "--request-json",
            str(paths["request"]),
            "--research-plan-json",
            str(paths["plan"]),
            "--identification-audit-json",
            str(paths["audit"]),
            "--data-requirements-json",
            str(paths["requirements"]),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["plan_id"] == plan["plan_id"]
    assert validate_bundle(output)["valid"] is True


def test_quick_validate_checks_execution_ready_artifact() -> None:
    run = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/quick_validate.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(run.stdout)

    assert run.returncode == 0, run.stderr
    assert report["execution_ready_bundle_valid"] is True
