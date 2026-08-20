from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from robustness_audit.exporter import (
    build_manifest,
    publish_directory,
    sha256_file,
    validate_bundle,
    write_json,
)
from robustness_audit.pipeline import _validate_inputs, run_robustness_audit
from robustness_audit.plan_compiler import compile_audit_plan
from robustness_audit.plotting import write_comparison_plot

ROOT = Path(__file__).resolve().parents[1]
TIME_SERIES_ROOT = ROOT.parent / "time-series-dynamics"
EXPECTED_FILES = {
    "audit-request.json",
    "audit-plan.json",
    "audit-result.json",
    "check-results.json",
    "comparison-paths.csv",
    "comparison-paths.png",
    "technical-summary.md",
    "plain-language-summary.md",
    "run-manifest.json",
}


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


def _content_id(prefix: str, document: object) -> str:
    return f"{prefix}-{_canonical_sha256(document)[:32]}"


def _reidentify_handoff(document: dict[str, object]) -> None:
    payload = {
        key: value
        for key, value in document.items()
        if key not in {"handoff_id", "checksum"}
    }
    document["handoff_id"] = f"rd-robustness-{_canonical_sha256(payload)[:32]}"
    checksum_payload = {
        key: value for key, value in document.items() if key != "checksum"
    }
    document["checksum"] = f"sha256:{_canonical_sha256(checksum_payload)}"


def _without_runtime_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_runtime_fields(item)
            for key, item in value.items()
            if key
            not in {
                "duration_seconds",
                "execution_error",
                "generated_at",
                "stderr",
                "stdout",
            }
        }
    if isinstance(value, list):
        return [_without_runtime_fields(item) for item in value]
    return value


def _semantic_directory_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(str(item.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        payload = item.read_bytes()
        if item.suffix == ".json":
            document = json.loads(payload)
            payload = json.dumps(
                _without_runtime_fields(document),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8") + b"\n"
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _semantic_file_sha256(path: Path) -> str:
    payload = path.read_bytes()
    if path.suffix == ".json":
        payload = json.dumps(
            _without_runtime_fields(json.loads(payload)),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8") + b"\n"
    return hashlib.sha256(payload).hexdigest()


def _resign_manifest(output: Path, changed: tuple[str, ...]) -> None:
    manifest = _load(output / "run-manifest.json")
    checksums = manifest["output_checksums"]
    assert isinstance(checksums, dict)
    for filename in changed:
        checksums[filename] = sha256_file(output / filename)
    fingerprint = {
        "audit_request_ref": manifest["audit_request_ref"],
        "audit_plan_ref": manifest["audit_plan_ref"],
        "inputs": manifest["input_checksums"],
        "outputs": {
            filename: _semantic_file_sha256(output / filename)
            for filename in sorted(EXPECTED_FILES - {"run-manifest.json"})
        },
        "alternatives": {
            item.name: _semantic_directory_sha256(item)
            for item in sorted(
                (output / "alternative-bundles").iterdir()
            )
            if item.is_dir()
        },
    }
    manifest["run_id"] = f"ra-run-{_canonical_sha256(fingerprint)[:32]}"
    write_json(output / "run-manifest.json", manifest)


def _documents() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    request = _load(ROOT / "fixtures" / "synthetic" / "audit-request.json")
    handoff = _load(
        ROOT / "fixtures" / "external" / "jel-example5.robustness-handoff.json"
    )
    baseline = _load(
        TIME_SERIES_ROOT / "fixtures" / "synthetic" / "jel.causal.request.json"
    )
    plan = compile_audit_plan(
        request,
        handoff,
        baseline,
        _load(ROOT / "fixtures" / "synthetic" / "adapter-capability.json"),
    )
    return request, handoff, plan


def _inputs() -> dict[str, Path]:
    fixtures = TIME_SERIES_ROOT / "fixtures" / "synthetic"
    return {
        "request": fixtures / "jel.causal.request.json",
        "research_plan": fixtures / "jel.causal.plan.json",
        "macro_data": fixtures / "jel.macro-result.json",
        "shock_artifact": fixtures / "jel.shock-artifact.json",
        "data": (
            TIME_SERIES_ROOT
            / ".cache"
            / "jorda-taylor-example5"
            / "aggregatedata_final.dta"
        ),
    }


def _run(tmp_path: Path) -> Path:
    request, handoff, plan = _documents()
    output = tmp_path / "audit"
    run_robustness_audit(
        request,
        plan,
        handoff,
        TIME_SERIES_ROOT / ".artifacts" / "jel-example5-causal",
        _inputs(),
        _load(ROOT / "fixtures" / "synthetic" / "adapter-capability.json"),
        TIME_SERIES_ROOT,
        output,
    )
    return output


@pytest.fixture(scope="module")
def audit_bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _run(tmp_path_factory.mktemp("audit-bundle"))


def test_pipeline_exports_complete_transactional_bundle(
    audit_bundle: Path,
) -> None:
    output = audit_bundle

    assert {path.name for path in output.iterdir() if path.is_file()} == EXPECTED_FILES
    alternatives = output / "alternative-bundles"
    assert len([path for path in alternatives.iterdir() if path.is_dir()]) == 7
    assert validate_bundle(output) == {"valid": True, "errors": []}
    with Image.open(output / "comparison-paths.png") as image:
        assert image.size == (1200, 720)
        assert any(low != high for low, high in image.convert("RGB").getextrema())


def test_manifest_run_id_ignores_nested_generated_timestamps(
    tmp_path: Path,
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    for filename in EXPECTED_FILES - {"run-manifest.json"}:
        (staging / filename).write_bytes(b"stable")
    write_json(staging / "check-results.json", {"duration_seconds": 1.0})
    alternative = staging / "alternative-bundles" / "ra-alt-stable"
    alternative.mkdir(parents=True)
    write_json(
        alternative / "run-manifest.json",
        {"generated_at": "2026-08-16T00:00:00Z", "result": "stable"},
    )
    first = build_manifest(staging, "ra-request-stable", "ra-plan-stable", {})
    write_json(staging / "check-results.json", {"duration_seconds": 2.0})
    write_json(
        alternative / "run-manifest.json",
        {"generated_at": "2026-08-16T00:00:01Z", "result": "stable"},
    )
    second = build_manifest(staging, "ra-request-stable", "ra-plan-stable", {})

    assert first["run_id"] == second["run_id"]
    assert (
        first["alternative_bundle_checksums"]
        != second["alternative_bundle_checksums"]
    )


def test_bundle_validator_detects_tampering(
    audit_bundle: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "tampered"
    shutil.copytree(audit_bundle, output)
    with (output / "check-results.json").open("ab") as handle:
        handle.write(b"tampered")

    result = validate_bundle(output)

    assert result["valid"] is False
    assert "checksum_mismatch:check-results.json" in result["errors"]


def test_bundle_validator_returns_errors_for_malformed_check_results(
    audit_bundle: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "malformed-checks"
    shutil.copytree(audit_bundle, output)
    write_json(output / "check-results.json", {"unexpected": 1})

    result = validate_bundle(output)

    assert result["valid"] is False
    assert "contract_violation:check-results.json" in result["errors"]


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("missing", "artifact_missing:audit-result.json"),
        ("unexpected", "artifact_unexpected:unplanned.txt"),
        ("alternatives", "alternative_bundles_missing"),
    ],
)
def test_bundle_validator_rejects_incomplete_artifact_sets(
    audit_bundle: Path,
    tmp_path: Path,
    mutation: str,
    expected_error: str,
) -> None:
    output = tmp_path / mutation
    shutil.copytree(audit_bundle, output)
    if mutation == "missing":
        (output / "audit-result.json").unlink()
    elif mutation == "unexpected":
        (output / "unplanned.txt").write_text("unplanned", encoding="utf-8")
    else:
        shutil.rmtree(output / "alternative-bundles")

    result = validate_bundle(output)

    assert result["valid"] is False
    assert expected_error in result["errors"]


def test_bundle_validator_rejects_invalid_png_content(
    audit_bundle: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "invalid-png"
    shutil.copytree(audit_bundle, output)
    png = output / "comparison-paths.png"
    png.write_bytes(b"not-a-png")
    manifest = _load(output / "run-manifest.json")
    checksums = manifest["output_checksums"]
    assert isinstance(checksums, dict)
    checksums["comparison-paths.png"] = sha256_file(png)
    write_json(output / "run-manifest.json", manifest)

    result = validate_bundle(output)

    assert result["valid"] is False
    assert "png_invalid" in result["errors"]


def test_bundle_validator_binds_alternative_directories_to_plan(
    audit_bundle: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "missing-planned-alternative"
    shutil.copytree(audit_bundle, output)
    plan = _load(output / "audit-plan.json")
    alternative_id = plan["alternatives"][0]["alternative_id"]  # type: ignore[index]
    shutil.rmtree(output / "alternative-bundles" / str(alternative_id))
    manifest = _load(output / "run-manifest.json")
    checksums = manifest["alternative_bundle_checksums"]
    assert isinstance(checksums, dict)
    checksums.pop(str(alternative_id))
    write_json(output / "run-manifest.json", manifest)
    _resign_manifest(output, ())

    validation = validate_bundle(output)

    assert validation["valid"] is False
    assert "planned_alternative_set_mismatch" in validation["errors"]


def test_bundle_validator_requires_deterministic_plain_summary(
    audit_bundle: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "summary-tamper"
    shutil.copytree(audit_bundle, output)
    (output / "plain-language-summary.md").write_text(
        "# 已声明稳健性检查\n\n结论已被替换。\n",
        encoding="utf-8",
    )
    _resign_manifest(output, ("plain-language-summary.md",))

    validation = validate_bundle(output)

    assert validation["valid"] is False
    assert "plain_summary_mismatch" in validation["errors"]


def test_publish_cleanup_failure_does_not_reverse_committed_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "published"
    output.mkdir()
    (output / "version.txt").write_text("old", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "version.txt").write_text("new", encoding="utf-8")
    monkeypatch.setattr(
        shutil,
        "rmtree",
        lambda path: (_ for _ in ()).throw(OSError(str(path))),
    )

    publish_directory(staging, output)

    assert (output / "version.txt").read_text(encoding="utf-8") == "new"


def test_plotting_writes_failure_evidence_without_comparison_rows(
    tmp_path: Path,
) -> None:
    path = tmp_path / "failed-audit.png"

    write_comparison_plot(path, [], "post_result_exploratory")

    with Image.open(path) as image:
        assert image.size == (1200, 720)


def test_plotting_discloses_post_result_exploratory_timing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "post-result-audit.png"
    rows = [
        {
            "alternative_id": "ra-alt-example",
            "horizon": 0,
            "baseline_estimate": 0.1,
            "alternative_estimate": 0.2,
        }
    ]

    write_comparison_plot(path, rows, "post_result_exploratory")

    with Image.open(path) as image:
        assert image.info["Description"] == (
            "Exploratory checks declared after baseline result review; "
            "not preregistered"
        )


def test_bundle_validator_recomputes_assessment_after_coordinated_tamper(
    audit_bundle: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "forced-pass"
    shutil.copytree(audit_bundle, output)
    checks = json.loads((output / "check-results.json").read_text(encoding="utf-8"))
    assert isinstance(checks, list)
    changed = checks[1]
    changed["status"] = "error"
    changed["execution_error"] = "forced failure"
    changed.pop("check_result_id")
    changed["check_result_id"] = _content_id("ra-check-result", changed)
    write_json(output / "check-results.json", checks)
    result = _load(output / "audit-result.json")
    result["check_result_refs"] = [item["check_result_id"] for item in checks]
    result["audit_result_id"] = _content_id(
        "ra-result",
        {
            "audit_plan_ref": result["audit_plan_ref"],
            "check_result_refs": result["check_result_refs"],
            "assessment": result["assessment"],
        },
    )
    write_json(output / "audit-result.json", result)
    _resign_manifest(
        output,
        ("audit-result.json", "check-results.json"),
    )

    validation = validate_bundle(output)

    assert validation["valid"] is False
    assert "assessment_mismatch" in validation["errors"]


def test_bundle_validator_rejects_manifest_identity_tamper(
    audit_bundle: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "manifest-tamper"
    shutil.copytree(audit_bundle, output)
    manifest = _load(output / "run-manifest.json")
    inputs = manifest["input_checksums"]
    assert isinstance(inputs, dict)
    inputs["baseline_data"] = "0" * 64
    write_json(output / "run-manifest.json", manifest)

    validation = validate_bundle(output)

    assert validation["valid"] is False
    assert "manifest_identity_mismatch" in validation["errors"]


def test_bundle_validator_rejects_audit_plan_checksum_tamper(
    audit_bundle: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "plan-tamper"
    shutil.copytree(audit_bundle, output)
    plan = _load(output / "audit-plan.json")
    plan["created_at"] = "2026-08-16T23:59:59Z"
    write_json(output / "audit-plan.json", plan)
    _resign_manifest(output, ("audit-plan.json",))

    validation = validate_bundle(output)

    assert validation["valid"] is False
    assert "audit_plan_checksum_mismatch" in validation["errors"]


def test_bundle_validator_rejects_causal_upgrade_from_associational_plan(
    audit_bundle: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "causal-upgrade"
    shutil.copytree(audit_bundle, output)
    plan = _load(output / "audit-plan.json")
    plan["claim_eligibility"] = "associational_only"
    payload = {key: value for key, value in plan.items() if key != "checksum"}
    plan["checksum"] = f"sha256:{_canonical_sha256(payload)}"
    write_json(output / "audit-plan.json", plan)
    _resign_manifest(output, ("audit-plan.json",))

    validation = validate_bundle(output)

    assert validation["valid"] is False
    assert "claim_eligibility_mismatch" in validation["errors"]


def test_validate_bundle_cli_reports_valid(audit_bundle: Path) -> None:
    run = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/validate_bundle.py",
            str(audit_bundle),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {"valid": True, "errors": []}


def test_run_cli_writes_complete_bundle(tmp_path: Path) -> None:
    _, _, plan = _documents()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    output = tmp_path / "cli-audit"
    run = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/run_robustness_audit.py",
            "--audit-request-json",
            "fixtures/synthetic/audit-request.json",
            "--audit-plan-json",
            str(plan_path),
            "--handoff-json",
            "fixtures/external/jel-example5.robustness-handoff.json",
            "--baseline-bundle",
            str(TIME_SERIES_ROOT / ".artifacts" / "jel-example5-causal"),
            "--request",
            str(_inputs()["request"]),
            "--research-plan",
            str(_inputs()["research_plan"]),
            "--macro-result",
            str(_inputs()["macro_data"]),
            "--shock-artifact",
            str(_inputs()["shock_artifact"]),
            "--data",
            str(_inputs()["data"]),
            "--adapter-capability-json",
            "fixtures/synthetic/adapter-capability.json",
            "--adapter-root",
            str(TIME_SERIES_ROOT),
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
    assert validate_bundle(output) == {"valid": True, "errors": []}


def test_invalid_handoff_preserves_existing_output(tmp_path: Path) -> None:
    request, handoff, plan = _documents()
    invalid = copy.deepcopy(handoff)
    invalid["checksum"] = "sha256:" + "0" * 64
    output = tmp_path / "existing"
    output.mkdir()
    (output / "sentinel.txt").write_text("old", encoding="utf-8")

    with pytest.raises(ValueError, match="handoff"):
        run_robustness_audit(
            request,
            plan,
            invalid,
            TIME_SERIES_ROOT / ".artifacts" / "jel-example5-causal",
            _inputs(),
            _load(ROOT / "fixtures" / "synthetic" / "adapter-capability.json"),
            TIME_SERIES_ROOT,
            output,
        )

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "old"


def test_pipeline_rejects_mismatched_explicit_adapter_capability(
    tmp_path: Path,
) -> None:
    request, handoff, plan = _documents()
    capability = _load(
        ROOT / "fixtures" / "synthetic" / "adapter-capability.json"
    )
    capability["adapter_id"] = "other-estimator"

    with pytest.raises(ValueError, match="adapter capability mismatch"):
        run_robustness_audit(
            request,
            plan,
            handoff,
            TIME_SERIES_ROOT / ".artifacts" / "jel-example5-causal",
            _inputs(),
            capability,
            TIME_SERIES_ROOT,
            tmp_path / "audit",
        )


def test_pipeline_rejects_handoff_unrelated_to_request_and_plan() -> None:
    request, handoff, plan = _documents()
    unrelated = copy.deepcopy(handoff)
    unrelated["review_required"] = False
    _reidentify_handoff(unrelated)

    with pytest.raises(ValueError, match="handoff reference mismatch"):
        _validate_inputs(
            request,
            plan,
            unrelated,
            _load(ROOT / "fixtures" / "synthetic" / "adapter-capability.json"),
            TIME_SERIES_ROOT / ".artifacts" / "jel-example5-causal",
        )

    wrong_baseline = copy.deepcopy(request)
    wrong_baseline["baseline_request_ref"] = "tsd-request-fedcba9876543210"
    with pytest.raises(ValueError, match="baseline request reference mismatch"):
        _validate_inputs(
            wrong_baseline,
            plan,
            handoff,
            _load(ROOT / "fixtures" / "synthetic" / "adapter-capability.json"),
            TIME_SERIES_ROOT / ".artifacts" / "jel-example5-causal",
        )
