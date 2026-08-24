"""Write sanitized audit evidence for DataPro batch execution."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from macro_data.bundle_export import _sanitized
from macro_data.datapro_batch_plan import DataProBatch
from macro_data.primary_cell_ledger import PrimaryCellLedger


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _sanitized(document),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def write_batch_ledgers(
    output_dir: Path,
    batch: DataProBatch,
    evaluation: dict[str, Any],
    ledger: PrimaryCellLedger,
    missing: tuple[str, ...],
) -> None:
    selected = cast(list[dict[str, Any]], evaluation.get("selected_items") or [])
    filtered = cast(
        list[dict[str, Any]],
        evaluation.get("filtered_candidates") or [],
    )
    _write_json(
        output_dir / "candidate-ledgers" / f"{batch.batch_id}.json",
        {
            "schema_version": "0.1.0",
            "batch_id": batch.batch_id,
            "selected_count": len(selected),
            "filtered_count": len(filtered),
            "selected_items": selected,
            "filtered_candidates": filtered,
            "issue_codes": list(evaluation.get("issue_codes") or []),
        },
    )
    _write_json(
        output_dir / "coverage-ledgers" / f"{batch.batch_id}.json",
        {
            "schema_version": "0.1.0",
            "batch_id": batch.batch_id,
            "entity_code": batch.entity_code,
            "indicator_code": batch.indicator_code,
            "frequency": batch.frequency,
            "expected_periods": list(batch.periods),
            "locked_periods": [item.key.period for item in ledger.locked],
            "missing_periods": list(missing),
            "issue_codes": list(ledger.issue_codes),
        },
    )


def write_batch_plan(
    output_dir: Path,
    batches: Sequence[DataProBatch],
    *,
    maximum_calls: int,
    executed_call_count: int,
) -> None:
    _write_json(
        output_dir / "batch-plan.json",
        {
            "schema_version": "0.1.0",
            "maximum_calls": maximum_calls,
            "executed_call_count": executed_call_count,
            "batches": [batch.as_document() for batch in batches],
        },
    )
