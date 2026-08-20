from __future__ import annotations

import csv
import hashlib
import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from research_synthesis.exporter import validate_bundle
from research_synthesis.pipeline import run_research_synthesis

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
EXTERNAL = ROOT / "fixtures" / "external"
ESTIMATOR = (
    PROJECT_ROOT
    / "30_宏观经济实证Skill"
    / "02_模块开发"
    / "time-series-dynamics"
    / ".artifacts"
    / "jel-example5-causal"
)


def _load(path: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )


def _audit(package: Path, filename: str) -> dict[str, object]:
    return _load(package / ".audit" / filename)


def _write_json(path: Path, document: dict[str, object]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _resign_physical_manifest(package: Path) -> None:
    manifest_path = package / ".audit" / "run-manifest.json"
    manifest = _load(manifest_path)
    manifest["output_checksums"] = {
        path.relative_to(package).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(package.rglob("*"))
        if path.is_file() and path != manifest_path
    }
    _write_json(manifest_path, manifest)


def _mutate_package(package: Path, mutation: str) -> None:
    evidence = package / "reproduction" / "data-and-evidence"
    if mutation == "estimate":
        path = evidence / "estimator" / "result.json"
        document = _load(path)
        rows = cast(list[dict[str, object]], document["horizon_results"])
        rows[0]["estimate"] = 999.0
        _write_json(path, document)
    elif mutation == "limitation":
        path = package / ".audit" / "limitations.json"
        document = _load(path)
        limitations = cast(list[dict[str, object]], document["limitations"])
        document["limitations"] = limitations[1:]
        _write_json(path, document)
    elif mutation == "report":
        path = package / "research-report.md"
        report = path.read_text(encoding="utf-8")
        path.write_text(
            report.replace(
                "本研究报告保留 `causal_candidate` 和 `review_required` 边界。",
                "本研究已经确认全部结果。",
            ),
            encoding="utf-8",
        )
    elif mutation == "claim":
        path = package / ".audit" / "claim-ledger.json"
        document = _load(path)
        claims = cast(list[dict[str, object]], document["claims"])
        claims[0]["claim_eligibility"] = "associational_only"
        _write_json(path, document)
    elif mutation == "baseline":
        path = evidence / "robustness-audit" / "audit-result.json"
        document = _load(path)
        document["baseline_request_ref"] = "tsd-request-fedcba9876543210"
        _write_json(path, document)
    elif mutation == "audit_check":
        path = evidence / "robustness-audit" / "check-results.json"
        checks = cast(list[object], json.loads(path.read_text(encoding="utf-8")))
        path.write_text(
            json.dumps(checks[:-1], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    elif mutation == "data":
        (evidence / "macro-data" / "aggregatedata_final.dta").write_bytes(
            b"tampered data"
        )
    elif mutation == "secret":
        path = package / "reproduction" / "README.md"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n"
            + "Bearer "
            + "abcdefgh12345678\n",
            encoding="utf-8",
        )
    elif mutation == "unexpected":
        _write_json(package / "extra.json", {"unexpected": True})
    else:
        raise AssertionError(f"unknown mutation: {mutation}")
    _resign_physical_manifest(package)


def _report_rows(report: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in report.splitlines():
        if not line.startswith("| ") or line.startswith("| horizon"):
            continue
        values = [value.strip() for value in line.strip("|").split("|")]
        if values[0].startswith("---"):
            continue
        rows.append(
            dict(
                zip(
                    (
                        "horizon",
                        "estimate",
                        "standard_error",
                        "confidence_lower",
                        "confidence_upper",
                        "nobs",
                        "df_resid",
                    ),
                    values,
                    strict=True,
                )
            )
        )
    return rows


@pytest.fixture(scope="module")
def jel_package(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, object], Path]:
    output = tmp_path_factory.mktemp("jel-synthesis") / "package"
    result = run_research_synthesis(
        request=_load(EXTERNAL / "jel-example5.synthesis-request.json"),
        adapter_capabilities=_load(
            ROOT / "configs" / "local-upstream-adapters.json"
        ),
        project_root=PROJECT_ROOT,
        output_dir=output,
    )
    return result, output


@pytest.mark.external
def test_jel_report_answers_the_research_question(
    jel_package: tuple[dict[str, object], Path],
) -> None:
    result, package = jel_package
    report = (package / "research-report.md").read_text(encoding="utf-8")

    assert result["execution_status"] == "success"
    assert result["synthesis_readiness"] == "review_required"
    assert result["delivery_eligibility"] == "evidence_only"
    assert result["reproduction_status"] == "verified"
    assert result["release_recommendation"] == "stop_ship"
    assert "## 1. 研究问题" in report
    assert "## 4. 主要结果" in report
    assert "## 6. 结论与限制" in report
    assert "1985Q1" in report
    assert "2007Q4" in report
    assert "post-result" in report
    assert "pointwise" in report
    assert "因果关系已经确定" not in report
    reproduction = _audit(package, "reproduction-manifest.json")
    steps = cast(list[dict[str, object]], reproduction["steps"])
    assert cast(list[str], steps[0]["argv"])[0] == "python3"
    assert validate_bundle(package) == {"valid": True, "errors": []}


@pytest.mark.external
def test_jel_report_table_and_csv_equal_upstream_result_exactly(
    jel_package: tuple[dict[str, object], Path],
) -> None:
    _, package = jel_package
    report = (package / "research-report.md").read_text(encoding="utf-8")
    report_rows = _report_rows(report)
    with (package / "tables" / "dynamic-path.csv").open(
        encoding="utf-8",
        newline="",
    ) as handle:
        csv_rows = list(csv.DictReader(handle))
    result_rows = cast(
        list[dict[str, object]],
        _load(ESTIMATOR / "result.json")["horizon_results"],
    )

    assert len(report_rows) == len(csv_rows) == len(result_rows) == 18
    for report_row, csv_row, result_row in zip(
        report_rows,
        csv_rows,
        result_rows,
        strict=True,
    ):
        for field in report_row:
            assert Decimal(report_row[field]) == Decimal(csv_row[field])
            assert Decimal(csv_row[field]) == Decimal(str(result_row[field]))


@pytest.mark.external
def test_jel_package_does_not_expose_absolute_user_paths(
    jel_package: tuple[dict[str, object], Path],
) -> None:
    _, package = jel_package
    findings = []
    for path in package.rglob("*"):
        if not path.is_file() or path.suffix in {".dta", ".png", ".pyc"}:
            continue
        if "/" + "Users/" in path.read_text(
            encoding="utf-8",
            errors="ignore",
        ):
            findings.append(path.relative_to(package).as_posix())

    assert findings == []


@pytest.mark.external
def test_jel_scientific_identity_is_deterministic_across_reruns(
    jel_package: tuple[dict[str, object], Path],
    tmp_path: Path,
) -> None:
    first_result, first = jel_package
    second_result = run_research_synthesis(
        request=_load(EXTERNAL / "jel-example5.synthesis-request.json"),
        adapter_capabilities=_load(
            ROOT / "configs" / "local-upstream-adapters.json"
        ),
        project_root=PROJECT_ROOT,
        output_dir=tmp_path / "rerun",
    )
    second = Path(cast(str, second_result["output_dir"]))

    assert first_result["result_id"] == second_result["result_id"]
    assert _audit(first, "run-manifest.json")["run_id"] == (
        _audit(second, "run-manifest.json")["run_id"]
    )
    for filename, collection, id_field in (
        ("claim-ledger.json", "claims", "claim_id"),
        ("evidence-index.json", "evidence", "evidence_id"),
        ("limitations.json", "limitations", "limitation_id"),
    ):
        first_items = cast(list[dict[str, object]], _audit(first, filename)[collection])
        second_items = cast(
            list[dict[str, object]],
            _audit(second, filename)[collection],
        )
        assert [item[id_field] for item in first_items] == [
            item[id_field] for item in second_items
        ]
    for relative in (
        "research-report.md",
        "tables/dynamic-path.csv",
        "figures/dynamic-path.png",
    ):
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


@pytest.mark.external
@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            "estimate",
            (
                "evidence_artifact_checksum_mismatch:"
                "reproduction/data-and-evidence/estimator/result.json"
            ),
        ),
        ("limitation", "limitations_id_mismatch"),
        (
            "report",
            "reproduction_output_checksum_mismatch:research-report.md",
        ),
        ("claim", "claim_id_mismatch"),
        (
            "baseline",
            (
                "evidence_artifact_checksum_mismatch:"
                "reproduction/data-and-evidence/robustness-audit/"
                "audit-result.json"
            ),
        ),
        (
            "audit_check",
            (
                "evidence_artifact_checksum_mismatch:"
                "reproduction/data-and-evidence/robustness-audit/"
                "check-results.json"
            ),
        ),
        (
            "data",
            (
                "source_bundle_checksum_mismatch:"
                "macro-data/aggregatedata_final.dta"
            ),
        ),
        ("secret", "secret_like_value:reproduction/README.md"),
        ("unexpected", "artifact_unexpected:extra.json"),
    ],
)
def test_jel_coordinated_mutations_are_rejected(
    jel_package: tuple[dict[str, object], Path],
    tmp_path: Path,
    mutation: str,
    expected_error: str,
) -> None:
    _, source = jel_package
    package = tmp_path / mutation
    shutil.copytree(source, package)
    _mutate_package(package, mutation)

    result = validate_bundle(package)

    assert result["valid"] is False
    assert expected_error in result["errors"]
