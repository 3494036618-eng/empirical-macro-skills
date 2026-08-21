"""加载并验证 research-synthesis 边界合同。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_FILES = {
    "adapter_capability": "adapter-capability.schema.json",
    "bundle_reference": "bundle-reference.schema.json",
    "claim_ledger": "claim-ledger.schema.json",
    "evidence_index": "evidence-index.schema.json",
    "limitations": "limitations.schema.json",
    "reproduction_manifest": "reproduction-manifest.schema.json",
    "request": "research-synthesis-request.schema.json",
    "result": "research-synthesis-result.schema.json",
    "run_manifest": "research-synthesis-run-manifest.schema.json",
}
PACKAGE_SCHEMA_ROOT = Path(__file__).resolve().parent / "schemas"
SOURCE_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"
SCHEMA_ROOT = (
    PACKAGE_SCHEMA_ROOT
    if PACKAGE_SCHEMA_ROOT.is_dir()
    else SOURCE_SCHEMA_ROOT
)


@lru_cache(maxsize=len(SCHEMA_FILES))
def load_schema(contract: str) -> dict[str, object]:
    """读取并检查一份冻结 Schema。"""
    filename = SCHEMA_FILES.get(contract)
    if filename is None:
        raise KeyError(f"unsupported contract: {contract}")
    document = cast(
        dict[str, object],
        json.loads((SCHEMA_ROOT / filename).read_text(encoding="utf-8")),
    )
    Draft202012Validator.check_schema(document)
    return document


def validate_document(contract: str, document: dict[str, object]) -> None:
    """按 Draft 2020-12 验证结构化 Artifact。"""
    Draft202012Validator(
        load_schema(contract),
        format_checker=FormatChecker(),
    ).validate(document)
