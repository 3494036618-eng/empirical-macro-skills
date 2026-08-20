from __future__ import annotations

import argparse
import copy
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import FIXTURES, PROJECT_ROOT

REQUEST = FIXTURES / "completion" / "request.valid.json"


def _load_request() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(REQUEST.read_text(encoding="utf-8")),
    )


def _run_cli(
    *args: str,
    home: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.pop("DATAPRO_AGENT_PLAN_KEY", None)
    if home is not None:
        environment["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, "scripts/run_datapro_first.py", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def _candidate(period: str, *, provider: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "series_key": (
            "WORLD_BANK|World Development Indicators|CHN|FP.CPI.TOTL"
        ),
        "source_system": "WORLD_BANK",
        "dataset_id": "2",
        "dataset_name": "World Development Indicators",
        "entity_code": "CHN",
        "entity_name": "China",
        "indicator_code": "FP.CPI.TOTL",
        "indicator_name": "Consumer price index",
        "time_raw": period,
        "time_grain": "year",
        "observed_frequency": "A",
        "value": 100.0 + int(period) - 2019,
        "unit": {"value": "index", "status": "source_documented"},
        "seasonal_adjustment": {"value": None, "status": "not_applicable"},
        "price_basis": {
            "value": {
                "type": "index",
                "base_period": None,
                "chain_linked": None,
            },
            "status": "source_documented",
        },
        "definition": {
            "value": "Consumer price index",
            "status": "source_provided",
        },
        "release_date": {"value": None, "status": "unresolved"},
        "vintage": {"value": None, "status": "unresolved"},
        "p_date": {"value": "2026-08-19", "semantics": "source_last_updated"},
        "license": {
            "id": "CC-BY-4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "World Bank",
            "use_status": "allowed",
            "allows_requested_use": True,
        },
    }


def _fixture(provider: str, periods: tuple[str, ...]) -> dict[str, Any]:
    return {
        "parsed": {
            "provider": provider,
            "execution": {"provider_code": 0, "message": "success"},
            "candidates": [
                _candidate(period, provider=provider)
                for period in periods
            ],
            "raw_response": {"items": []},
            "fixture_provenance": {},
        }
    }


def _write(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False),
        encoding="utf-8",
    )


def test_datapro_first_cli_dry_run_makes_no_network_calls(
    tmp_path: Path,
) -> None:
    output = tmp_path / "dry-run"

    result = _run_cli(
        "--request-json",
        str(REQUEST),
        "--output",
        str(output),
        home=tmp_path / "empty-home",
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "dry_run"
    assert summary["planned_primary_provider"] == "datapro"
    assert summary["expected_observation_count"] == 3
    assert not output.exists()


def test_datapro_first_cli_fixture_mode_exports_a_mixed_bundle(
    tmp_path: Path,
) -> None:
    datapro = tmp_path / "datapro.json"
    official = tmp_path / "world-bank.json"
    _write(datapro, _fixture("datapro", ("2019", "2021")))
    _write(official, _fixture("world_bank", ("2020",)))
    output = tmp_path / "bundle"

    result = _run_cli(
        "--request-json",
        str(REQUEST),
        "--output",
        str(output),
        "--datapro-fixture",
        str(datapro),
        "--official-fixture",
        str(official),
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "success"
    assert summary["provider_contribution"]["classification"] == (
        "datapro_assisted"
    )
    assert summary["bundle_valid"] is True
    assert (output / "completion_manifest.json").is_file()


def test_datapro_first_cli_live_requires_a_credential_before_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "live"

    result = _run_cli(
        "--request-json",
        str(REQUEST),
        "--output",
        str(output),
        "--live",
        home=tmp_path / "empty-home",
    )

    assert result.returncode != 0
    assert "credential is unavailable" in result.stderr
    assert not output.exists()


def test_datapro_first_cli_rejects_unapproved_official_fixture(
    tmp_path: Path,
) -> None:
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    typed_request = cast(dict[str, Any], copy.deepcopy(request))
    typed_request["preferred_sources"] = ["datapro"]
    typed_request["fallback_policy"]["mode"] = "never"
    typed_request["fallback_policy"]["allowed_sources"] = []
    request_path = tmp_path / "request.json"
    datapro = tmp_path / "datapro.json"
    official = tmp_path / "world-bank.json"
    _write(request_path, typed_request)
    _write(datapro, _fixture("datapro", ("2019", "2021")))
    _write(official, _fixture("world_bank", ("2020",)))
    output = tmp_path / "bundle"

    result = _run_cli(
        "--request-json",
        str(request_path),
        "--output",
        str(output),
        "--datapro-fixture",
        str(datapro),
        "--official-fixture",
        str(official),
    )

    assert result.returncode != 0
    assert "not allowed by fallback_policy" in result.stderr
    assert not output.exists()


def test_datapro_first_cli_directs_v02_requests_to_legacy_cli(
    tmp_path: Path,
) -> None:
    output = tmp_path / "legacy"
    legacy = FIXTURES / "synthetic" / "schema-examples" / "request.valid.json"

    result = _run_cli(
        "--request-json",
        str(legacy),
        "--output",
        str(output),
    )

    assert result.returncode != 0
    assert "scripts/run_macro_data.py" in result.stderr
    assert not output.exists()


def test_datapro_first_publish_restores_existing_bundle_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("scripts.run_datapro_first")
    datapro = tmp_path / "datapro.json"
    _write(datapro, _fixture("datapro", ("2019", "2021")))
    output = tmp_path / "bundle"
    output.mkdir()
    prior = output / "prior-valid.txt"
    prior.write_text("keep", encoding="utf-8")
    args = argparse.Namespace(
        live=False,
        datapro_fixture=datapro,
        official_fixture=None,
        output=output,
    )

    def fail_run(*, output_dir: Path, **_: Any) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "partial.txt").write_text("partial", encoding="utf-8")
        raise RuntimeError("synthetic completion failure")

    monkeypatch.setattr(module, "run_datapro_first_completion", fail_run)

    with pytest.raises(RuntimeError, match="synthetic completion failure"):
        module._execute(_load_request(), args)

    assert prior.read_text(encoding="utf-8") == "keep"
    assert not (output / "partial.txt").exists()
    assert not list(tmp_path.glob(".bundle.staging-*"))
