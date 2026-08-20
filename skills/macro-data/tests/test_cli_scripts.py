import importlib
import json
import subprocess
import sys
import tomllib

from conftest import FIXTURES, PROJECT_ROOT

REQUEST = (
    "查询中国 2019-01 至 2024-12 的月度居民消费价格指数 CPI。"
    "必须是月度，不要用年度数据替代；返回指标代码、实体代码、月份、单位和季调状态。"
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_script_generates_a_bundle_from_a_sanitized_live_fixture(tmp_path):
    output = tmp_path / "bundle"
    result = _run(
        "scripts/run_macro_data.py",
        "--request",
        REQUEST,
        "--fixture",
        str(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json"),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["research_readiness"] == "blocked"
    assert summary["delivery_eligibility"] == "not_deliverable"
    assert (output / "run_manifest.json").exists()


def test_run_script_uses_validated_request_json_as_authoritative_input(tmp_path):
    parser = importlib.import_module("macro_data.request_parser")
    request = parser.parse_research_request(REQUEST)
    request["research_use"] = "descriptive_latest"
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(request, ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "structured-bundle"

    result = _run(
        "scripts/run_macro_data.py",
        "--request-json",
        str(request_path),
        "--fixture",
        str(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json"),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    assert json.loads((output / "request_manifest.json").read_text(encoding="utf-8")) == request


def test_probe_script_inspects_fixture_offline_and_requires_explicit_live_flag():
    fixture = FIXTURES / "sanitized-live" / "05_ambiguous_nonexistent_indicator.json"
    inspected = _run(
        "scripts/probe_datapro.py",
        "--inspect-fixture",
        str(fixture),
    )
    blocked_live = _run(
        "scripts/probe_datapro.py",
        "--query",
        "中国年度 CPI",
    )

    assert inspected.returncode == 0, inspected.stderr
    summary = json.loads(inspected.stdout)
    assert summary["fixture_type"] == "sanitized-live"
    assert summary["dataset_type"] == "macro"
    assert summary["item_count"] == 0
    assert blocked_live.returncode != 0
    assert "--live" in blocked_live.stderr


def test_validate_script_returns_nonzero_after_bundle_tampering(tmp_path):
    output = tmp_path / "bundle"
    generated = _run(
        "scripts/run_macro_data.py",
        "--request",
        REQUEST,
        "--fixture",
        str(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json"),
        "--output",
        str(output),
    )
    assert generated.returncode == 0, generated.stderr

    valid = _run("scripts/validate_bundle.py", str(output))
    assert valid.returncode == 0
    assert json.loads(valid.stdout)["valid"] is True

    with (output / "data.csv").open("a", encoding="utf-8") as handle:
        handle.write("tampered\\n")
    invalid = _run("scripts/validate_bundle.py", str(output))
    assert invalid.returncode == 1
    assert "data.csv" in json.loads(invalid.stdout)["checksum_mismatches"]


def test_quick_validate_checks_the_skill_structure_and_contracts():
    result = _run("scripts/quick_validate.py")

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["valid"] is True
    assert report["frontmatter_keys"] == ["description", "name"]
    assert report["schema_count"] == 11
    assert report["secret_findings"] == []


def test_quick_validate_distinguishes_class_name_from_authorization_header():
    module = importlib.import_module("scripts.quick_validate")

    assert module.SECRET_PATTERN.search("class UseAuthorization:") is None
    header = "Author" + "ization: secret-value"
    assert module.SECRET_PATTERN.search(header)


def test_run_script_records_explicit_world_bank_approval_in_request_contract():
    module = importlib.import_module("scripts.run_macro_data")

    datapro_request = module._prepare_request(
        "查询中国 2019—2024 年年度 CPI。",
        "datapro",
    )
    world_bank_request = module._prepare_request(
        "严格查询 World Bank WDI 口径：中国 2019—2024 年年度 CPI。",
        "world_bank",
    )

    assert datapro_request["preferred_sources"] == ["datapro"]
    assert datapro_request["fallback_policy"]["mode"] == "never"
    assert world_bank_request["preferred_sources"] == ["datapro", "world_bank"]
    assert world_bank_request["fallback_policy"] == {
        "mode": "allow_official",
        "allowed_sources": ["world_bank"],
        "allow_semantic_substitute": False,
        "allow_cross_source_stitching": False,
    }


def test_pyproject_freezes_quality_gates() -> None:
    document = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = set(document["dependency-groups"]["dev"])

    assert "ruff==0.16.3" in dev
    assert "mypy==1.20.2" in dev
    assert "pytest-cov==7.1.0" in dev
    assert "types-jsonschema==4.26.0.20260518" in dev
    assert document["tool"]["mypy"]["strict"] is True
    assert document["tool"]["ruff"]["lint"]["mccabe"]["max-complexity"] == 10
    assert document["tool"]["pytest"]["ini_options"]["addopts"].endswith("--cov-fail-under=90")
