"""Host-neutral execution and publication of a live DataPro-first bundle."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from macro_data.completion_export import export_completion_bundle
from macro_data.completion_validation import validate_completion_bundle
from macro_data.connectors.base import Connector
from macro_data.contracts import validate_document
from macro_data.multi_source_pipeline import run_datapro_first_completion


def _publish(staging: Path, output: Path) -> None:
    backup: Path | None = None
    if output.exists():
        backup = output.with_name(f".{output.name}.backup")
        if backup.exists():
            shutil.rmtree(backup)
        os.replace(output, backup)
    try:
        os.replace(staging, output)
    except BaseException:
        if backup is not None and backup.exists() and not output.exists():
            os.replace(backup, output)
        raise
    finally:
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)


def run_live_completion(
    *,
    request: dict[str, object],
    datapro_connector: Connector,
    output_dir: Path,
    official_connectors: Mapping[str, Connector] | None = None,
) -> dict[str, object]:
    validated_request = cast(dict[str, Any], request)
    validate_document("request", validated_request)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.staging-",
            dir=output_dir.parent,
        )
    )
    try:
        run = run_datapro_first_completion(
            request=validated_request,
            datapro_connector=datapro_connector,
            official_connectors=official_connectors or {},
            output_dir=staging,
            input_mode="live",
        )
        export_completion_bundle(
            request=validated_request,
            result=run["completion"],
            retrievals=run["retrievals"],
            gap_manifest=run["gap_manifest"],
            output_dir=staging,
            input_mode="live",
        )
        validation = validate_completion_bundle(staging)
        if validation["valid"] is not True:
            raise RuntimeError("completion bundle validation failed")
        _publish(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return {
        "status": run["execution_status"],
        "research_readiness": run["research_readiness"],
        "delivery_eligibility": run["delivery_eligibility"],
        "eligible_for_estimation": run["eligible_for_estimation"],
        "provider_contribution": run["provider_contribution"],
        "issue_codes": run["issue_codes"],
        "bundle_valid": True,
    }
