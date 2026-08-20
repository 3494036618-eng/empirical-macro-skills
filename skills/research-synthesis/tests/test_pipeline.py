from __future__ import annotations

import copy
import importlib.util
from importlib import import_module
from pathlib import Path

import pytest

from research_synthesis.models import ReportInputs
from tests.factories import local_adapter_capabilities, real_request

ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_and_public_cli_surface_exists() -> None:
    assert importlib.util.find_spec("research_synthesis.pipeline") is not None
    for script in (
        "quick_validate.py",
        "run_research_synthesis.py",
        "validate_bundle.py",
    ):
        assert (ROOT / "scripts" / script).is_file()


def test_pipeline_builds_single_report_package(tmp_path: Path) -> None:
    module = import_module("research_synthesis.pipeline")
    assert hasattr(module, "run_research_synthesis")
    output = tmp_path / "package"

    result = module.run_research_synthesis(
        real_request(),
        local_adapter_capabilities(),
        ROOT.parents[2],
        output,
    )

    assert result["execution_status"] == "success"
    assert result["synthesis_readiness"] == "review_required"
    assert result["delivery_eligibility"] == "evidence_only"
    assert (output / "research-report.md").is_file()
    assert not (output / "plain-language-summary.md").exists()


def test_pipeline_returns_structured_failure_without_package(
    tmp_path: Path,
) -> None:
    module = import_module("research_synthesis.pipeline")
    request = copy.deepcopy(real_request())
    request["bundle_refs"][0]["expected_manifest_sha256"] = (  # type: ignore[index]
        "sha256:" + "0" * 64
    )
    output = tmp_path / "package"

    result = module.run_research_synthesis(
        request,
        local_adapter_capabilities(),
        ROOT.parents[2],
        output,
    )

    assert result["execution_status"] == "failed"
    assert result["synthesis_readiness"] == "blocked"
    assert result["delivery_eligibility"] == "not_deliverable"
    assert not output.exists()


def test_pipeline_fails_when_clean_reproduction_differs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("research_synthesis.pipeline")
    original = module.build_report
    calls = 0

    def drifting_report(inputs: ReportInputs) -> str:
        nonlocal calls
        calls += 1
        report = original(inputs)
        return report if calls == 1 else report + "\nreproduction drift\n"

    monkeypatch.setattr(module, "build_report", drifting_report)
    output = tmp_path / "package"

    result = module.run_research_synthesis(
        real_request(),
        local_adapter_capabilities(),
        ROOT.parents[2],
        output,
    )

    assert result["execution_status"] == "failed"
    assert result["issue_codes"] == [
        "reproduction_failed:research-report.md"
    ]
    assert not output.exists()


def test_pipeline_rejects_blocked_design_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("research_synthesis.pipeline")
    original = module.build_evidence_envelope

    def blocked_design(role: str, bundle: object) -> object:
        envelope = original(role, bundle)
        if role == "research_design":
            envelope.statuses["design_readiness"] = "blocked"
        return envelope

    monkeypatch.setattr(module, "build_evidence_envelope", blocked_design)
    output = tmp_path / "package"

    result = module.run_research_synthesis(
        real_request(),
        local_adapter_capabilities(),
        ROOT.parents[2],
        output,
    )

    assert result["execution_status"] == "failed"
    assert result["issue_codes"] == ["research_design_blocked"]
    assert not output.exists()


def test_pipeline_accepts_review_required_causal_design(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: every causal candidate is rejected before report synthesis."""
    module = import_module("research_synthesis.pipeline")
    original = module.build_evidence_envelope

    def reviewed_design(role: str, bundle: object) -> object:
        envelope = original(role, bundle)
        if role == "research_design":
            envelope.statuses["execution_status"] = "partial"
            envelope.statuses["design_readiness"] = "review_required"
            assert envelope.claim_eligibility == "causal_candidate"
        return envelope

    monkeypatch.setattr(module, "build_evidence_envelope", reviewed_design)
    output = tmp_path / "package"

    result = module.run_research_synthesis(
        real_request(),
        local_adapter_capabilities(),
        ROOT.parents[2],
        output,
    )

    assert result["execution_status"] == "success"
    assert result["synthesis_readiness"] == "review_required"
    assert result["delivery_eligibility"] == "evidence_only"
    assert (output / "research-report.md").is_file()
