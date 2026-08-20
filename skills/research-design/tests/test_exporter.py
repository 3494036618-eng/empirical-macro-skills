from __future__ import annotations

import json
from pathlib import Path

import pytest

import research_design.exporter as exporter
from research_design.exporter import validate_bundle
from research_design.pipeline import run_research_design
from research_design.readiness import evaluate_readiness


def test_export_failure_preserves_previous_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
    macro_schema_path: Path,
) -> None:
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "sentinel.txt").write_text("old", encoding="utf-8")

    def raising_writer(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected export failure")

    monkeypatch.setattr("research_design.exporter.write_artifact", raising_writer)
    with pytest.raises(RuntimeError, match="injected export failure"):
        run_research_design(
            valid_intake_document,
            valid_request_document,
            output,
            macro_schema_path,
        )

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "old"


def test_manifest_tamper_invalidates_bundle(
    tmp_path: Path,
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
    macro_schema_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    run_research_design(
        valid_intake_document,
        valid_request_document,
        bundle,
        macro_schema_path,
    )
    manifest_path = bundle / "research-design-run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["claim_eligibility"] = "causal_candidate"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_bundle(bundle)

    assert result["valid"] is False
    assert "manifest_plan_state_mismatch" in result["errors"]


def test_successful_bundle_validates(
    tmp_path: Path,
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
    macro_schema_path: Path,
) -> None:
    bundle = tmp_path / "bundle"

    summary = run_research_design(
        valid_intake_document,
        valid_request_document,
        bundle,
        macro_schema_path,
    )

    assert summary["output_dir"] == str(bundle)
    assert validate_bundle(bundle) == {"valid": True, "errors": []}


def test_readiness_never_auto_approves_causal_or_structural_candidates() -> None:
    for eligibility in ("causal_candidate", "structural_candidate"):
        result = evaluate_readiness(set(), eligibility)
        assert result["design_readiness"] == "review_required"
        assert result["review_required"] is True


def test_low_risk_readiness_requires_zero_issues() -> None:
    ready = evaluate_readiness(set(), "associational_only")
    blocked = evaluate_readiness({"missing_scope"}, "associational_only")
    ineligible = evaluate_readiness(set(), "not_eligible")

    assert ready == {
        "execution_status": "success",
        "design_readiness": "ready_for_data",
        "review_required": False,
    }
    assert blocked["design_readiness"] == "blocked"
    assert ineligible["design_readiness"] == "blocked"


def test_artifact_byte_tamper_breaks_checksum(
    tmp_path: Path,
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
    macro_schema_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    run_research_design(
        valid_intake_document,
        valid_request_document,
        bundle,
        macro_schema_path,
    )
    request_path = bundle / "research_request.json"
    request_path.write_bytes(request_path.read_bytes() + b" ")

    result = validate_bundle(bundle)

    assert result["valid"] is False
    assert "checksum_mismatch:research_request" in result["errors"]


def test_missing_artifact_invalidates_bundle(
    tmp_path: Path,
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
    macro_schema_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    run_research_design(
        valid_intake_document,
        valid_request_document,
        bundle,
        macro_schema_path,
    )
    (bundle / "data_requirements.json").unlink()

    result = validate_bundle(bundle)

    assert "artifact_missing:data_requirements" in result["errors"]


def test_repeated_publication_replaces_bundle_transactionally(
    tmp_path: Path,
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
    macro_schema_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    for _ in range(2):
        run_research_design(
            valid_intake_document,
            valid_request_document,
            bundle,
            macro_schema_path,
        )

    assert validate_bundle(bundle) == {"valid": True, "errors": []}


def test_backup_cleanup_failure_does_not_report_publish_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "sentinel.txt").write_text("old", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "sentinel.txt").write_text("new", encoding="utf-8")
    monkeypatch.setattr(
        exporter.shutil,
        "rmtree",
        lambda path: (_ for _ in ()).throw(OSError(str(path))),
    )

    exporter.publish_directory(staging, output)

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "new"


def test_descriptive_bundle_omits_identification_audit(
    tmp_path: Path,
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
    macro_schema_path: Path,
) -> None:
    valid_request_document.update(
        {
            "selected_candidate_id": "rd-candidate-aaaaaaaa",
            "intended_claim": "descriptive",
            "variables": [
                {
                    "variable_id": "inflation",
                    "role": "outcome",
                    "concept": "通胀",
                    "definition_constraints": [],
                }
            ],
            "intervention_or_shock": None,
        }
    )
    bundle = tmp_path / "bundle"

    run_research_design(
        valid_intake_document,
        valid_request_document,
        bundle,
        macro_schema_path,
    )
    manifest = json.loads(
        (bundle / "research-design-run-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["artifacts"]["identification_audit"] is None
    assert not (bundle / "identification_audit.json").exists()


def test_complete_causal_policy_design_remains_review_required(
    tmp_path: Path,
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
    macro_schema_path: Path,
) -> None:
    candidates = valid_intake_document["candidate_questions"]
    assert isinstance(candidates, list)
    selected = candidates[1]
    assert isinstance(selected, dict)
    selected["research_family_candidate"] = "causal_policy_evaluation"
    valid_request_document.update(
        {
            "variables": [
                {
                    "variable_id": "employment",
                    "role": "outcome",
                    "concept": "就业",
                    "definition_constraints": [],
                },
                {
                    "variable_id": "policy",
                    "role": "treatment",
                    "concept": "政策处理",
                    "definition_constraints": [],
                },
            ],
            "intervention_or_shock": {
                "name": "地区政策",
                "timing_known": True,
                "assignment_mechanism": "observational",
            },
            "comparison": "尚未接受政策的地区",
            "field_provenance": [
                {
                    "field_path": field,
                    "source": "user_provided",
                    "evidence_text": "完整政策设计fixture",
                    "confidence": "high",
                }
                for field in (
                    "research_question",
                    "intended_claim",
                    "target_population",
                    "unit_of_analysis",
                    "time_scope",
                    "variables[0].role",
                    "variables[1].role",
                )
            ],
            "design_audit_inputs": {
                "treatment_defined": True,
                "comparison_group_defined": True,
                "anticipation_assessed": True,
                "spillovers_assessed": True,
            },
        }
    )

    result = run_research_design(
        valid_intake_document,
        valid_request_document,
        tmp_path / "causal-policy",
        macro_schema_path,
    )

    assert result["claim_eligibility"] == "causal_candidate"
    assert result["design_readiness"] == "review_required"
