"""Run the 0.3 DataPro-first missing-only completion workflow."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, cast

from macro_data.completion_export import export_completion_bundle
from macro_data.completion_validation import validate_completion_bundle
from macro_data.connectors.base import Connector, ConnectorRequest, ConnectorResponse
from macro_data.connectors.datapro import DataProConnector
from macro_data.connectors.world_bank import WorldBankConnector
from macro_data.multi_source_pipeline import run_datapro_first_completion
from macro_data.observation_matrix import build_expected_matrix
from macro_data.request_loader import load_request_json
from macro_data.result_parser import (
    parse_datapro_response,
    parse_world_bank_response,
)


class FixtureConnector:
    """Offline connector for contract and integration fixtures."""

    def __init__(self, code: str, fixture: Path) -> None:
        self.code = code
        document = json.loads(fixture.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"{code} fixture must contain a JSON object")
        self._document = cast(dict[str, Any], document)

    def retrieve(self, request: ConnectorRequest) -> ConnectorResponse:
        return ConnectorResponse(
            provider=self.code,
            request_id=request.request_id,
            raw=copy.deepcopy(self._document),
            retrieved_at="fixture",
        )

    def parse_response(self, raw: dict[str, Any]) -> dict[str, Any]:
        parsed = raw.get("parsed")
        if isinstance(parsed, dict):
            return cast(dict[str, Any], copy.deepcopy(parsed))
        if self.code == "datapro":
            return parse_datapro_response(raw)
        return parse_world_bank_response(raw)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--datapro-fixture", type=Path)
    parser.add_argument("--official-fixture", type=Path)
    return parser


def _validate_mode(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    request: dict[str, Any],
) -> None:
    if request["schema_version"] != "0.3.0-beta":
        parser.error(
            "0.2 request must use the legacy CLI: scripts/run_macro_data.py"
        )
    has_fixture = args.datapro_fixture is not None or args.official_fixture is not None
    if args.live and has_fixture:
        parser.error("--live cannot be combined with fixture arguments")
    if args.official_fixture is not None and args.datapro_fixture is None:
        parser.error("--official-fixture requires --datapro-fixture")
    if args.official_fixture is not None:
        policy = request["fallback_policy"]
        if (
            policy["mode"] != "allow_official_missing_only"
            or "world_bank" not in policy["allowed_sources"]
        ):
            parser.error(
                "world_bank is not allowed by fallback_policy"
            )


def _dry_run(request: dict[str, Any]) -> dict[str, object]:
    matrix = build_expected_matrix(request)
    return {
        "status": "dry_run",
        "planned_primary_provider": "datapro",
        "allowed_official_providers": request["fallback_policy"][
            "allowed_sources"
        ],
        "expected_observation_count": len(matrix.cells),
        "matrix_id": matrix.matrix_id,
    }


def _connectors(
    args: argparse.Namespace,
    request: dict[str, Any],
) -> tuple[Connector, dict[str, Connector], str]:
    if args.live:
        live_official: dict[str, Connector] = (
            {"world_bank": WorldBankConnector()}
            if "world_bank" in request["fallback_policy"]["allowed_sources"]
            else {}
        )
        return DataProConnector(), live_official, "live"
    fixture_official: dict[str, Connector] = (
        {
            "world_bank": FixtureConnector(
                "world_bank",
                args.official_fixture,
            )
        }
        if args.official_fixture is not None
        else {}
    )
    return (
        FixtureConnector("datapro", args.datapro_fixture),
        fixture_official,
        "mock",
    )


def _execute(
    request: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, object]:
    datapro, official, input_mode = _connectors(args, request)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{args.output.name}.staging-",
            dir=args.output.parent,
        )
    )
    try:
        summary = _build_bundle(
            request=request,
            datapro=datapro,
            official=official,
            output=staging,
            input_mode=input_mode,
        )
        _publish_staging(staging, args.output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    summary["output"] = str(args.output)
    return summary


def _build_bundle(
    *,
    request: dict[str, Any],
    datapro: Connector,
    official: dict[str, Connector],
    output: Path,
    input_mode: str,
) -> dict[str, object]:
    run = run_datapro_first_completion(
        request=request,
        datapro_connector=datapro,
        official_connectors=official,
        output_dir=output,
        input_mode=input_mode,
    )
    export_completion_bundle(
        request=request,
        result=run["completion"],
        retrievals=run["retrievals"],
        gap_manifest=run["gap_manifest"],
        output_dir=output,
        input_mode=input_mode,
    )
    validation = validate_completion_bundle(output)
    if not validation["valid"]:
        raise RuntimeError("completion bundle validation failed")
    return {
        "status": run["execution_status"],
        "output": str(output),
        "research_readiness": run["research_readiness"],
        "delivery_eligibility": run["delivery_eligibility"],
        "eligible_for_estimation": run["eligible_for_estimation"],
        "provider_contribution": run["provider_contribution"],
        "issue_codes": run["issue_codes"],
        "bundle_valid": validation["valid"],
    }


def _publish_staging(staging: Path, output: Path) -> None:
    backup_root: Path | None = None
    backup: Path | None = None
    try:
        if output.exists():
            backup_root = Path(
                tempfile.mkdtemp(
                    prefix=f".{output.name}.backup-",
                    dir=output.parent,
                )
            )
            backup = backup_root / "previous"
            os.replace(output, backup)
        os.replace(staging, output)
    except Exception:
        if backup is not None and backup.exists() and not output.exists():
            os.replace(backup, output)
        raise
    finally:
        if backup_root is not None:
            shutil.rmtree(backup_root, ignore_errors=True)


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        request = load_request_json(args.request_json)
        _validate_mode(parser, args, request)
        if not args.live and args.datapro_fixture is None:
            summary = _dry_run(request)
        else:
            summary = _execute(request, args)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
