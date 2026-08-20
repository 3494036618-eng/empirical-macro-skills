from __future__ import annotations

import importlib.util
from importlib import import_module

from research_synthesis.contracts import validate_document
from tests.factories import real_envelopes


def test_ledger_compiler_modules_exist() -> None:
    for module in (
        "claim_compiler",
        "claim_policy",
        "evidence_index",
        "limitations",
    ):
        assert importlib.util.find_spec(f"research_synthesis.{module}") is not None


def test_evidence_index_uses_only_structured_locators() -> None:
    module = import_module("research_synthesis.evidence_index")
    assert hasattr(module, "compile_evidence_index")

    index = module.compile_evidence_index(real_envelopes())
    validate_document("evidence_index", index)
    evidence = index["evidence"]
    numeric = [
        item
        for item in evidence
        if item["semantic_role"] in {"estimate", "uncertainty"}
    ]

    assert len(numeric) == 72
    assert sum(item["semantic_role"] == "estimate" for item in numeric) == 18
    assert sum(item["semantic_role"] == "uncertainty" for item in numeric) == 54
    assert {
        item["locator"]["type"] for item in numeric
    } <= {"json_pointer", "csv_row_key"}
    assert not {
        "markdown_heading",
        "free_text_quote",
        "image_ocr",
    } & {item["locator"]["type"] for item in evidence}
