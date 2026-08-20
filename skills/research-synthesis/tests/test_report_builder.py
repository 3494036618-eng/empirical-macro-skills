from __future__ import annotations

import copy
import importlib.util
from importlib import import_module
from pathlib import Path

from research_synthesis.claim_compiler import compile_claim_ledger
from research_synthesis.claim_policy import assert_report_language
from research_synthesis.evidence_index import compile_evidence_index
from research_synthesis.limitations import compile_limitations
from research_synthesis.models import ReportInputs
from tests.conftest import FIXTURES, load_json
from tests.factories import MODULES, real_envelopes


def test_report_builder_module_exists() -> None:
    assert importlib.util.find_spec("research_synthesis.report_builder") is not None


def _inputs(
    envelopes: dict[str, object] | None = None,
) -> ReportInputs:
    typed_envelopes = (
        real_envelopes()
        if envelopes is None
        else envelopes
    )
    index = compile_evidence_index(typed_envelopes)  # type: ignore[arg-type]
    claims = compile_claim_ledger(typed_envelopes, index)  # type: ignore[arg-type]
    limits = compile_limitations(typed_envelopes, claims, index)  # type: ignore[arg-type]
    return ReportInputs(
        request=load_json(FIXTURES / "synthetic" / "request.valid.json"),
        evidence_index=index,
        claim_ledger=claims,
        limitations=limits,
        envelopes=typed_envelopes,  # type: ignore[arg-type]
    )


def test_report_has_six_professional_research_sections() -> None:
    module = import_module("research_synthesis.report_builder")
    assert hasattr(module, "build_report")

    report = module.build_report(_inputs())

    for heading in (
        "## 1. 研究问题",
        "## 2. 数据",
        "## 3. 方法",
        "## 4. 主要结果",
        "## 5. 稳健性",
        "## 6. 结论与限制",
    ):
        assert heading in report
    for expected in (
        "1985Q1",
        "2007Q4",
        "Local Projection",
        "95% pointwise interval",
        "passed_declared_checks",
        "post-result exploratory",
        "tables/dynamic-path.csv",
        "figures/dynamic-path.png",
    ):
        assert expected in report
    assert "技术版" not in report
    assert "大白话版" not in report
    assert_report_language(report, "causal_candidate")


def test_report_assets_are_byte_identical(tmp_path: Path) -> None:
    module = import_module("research_synthesis.report_builder")
    assert hasattr(module, "copy_report_assets")
    estimator = (
        MODULES
        / "time-series-dynamics"
        / ".artifacts"
        / "jel-example5-causal"
    )

    checksums = module.copy_report_assets(estimator, tmp_path)

    assert (tmp_path / "tables" / "dynamic-path.csv").read_bytes() == (
        estimator / "dynamic-path.csv"
    ).read_bytes()
    assert (tmp_path / "figures" / "dynamic-path.png").read_bytes() == (
        estimator / "dynamic-path.png"
    ).read_bytes()
    assert set(checksums) == {
        "tables/dynamic-path.csv",
        "figures/dynamic-path.png",
    }


def test_associational_report_does_not_use_causal_candidate_language() -> None:
    module = import_module("research_synthesis.report_builder")
    envelopes = copy.deepcopy(real_envelopes())
    object.__setattr__(
        envelopes["estimator"],
        "claim_eligibility",
        "associational_only",
    )
    object.__setattr__(
        envelopes["robustness_audit"],
        "claim_eligibility",
        "associational_only",
    )
    envelopes["estimator"].statuses["claim_eligibility"] = "associational_only"

    report = module.build_report(_inputs(envelopes))

    assert "条件动态关联" in report
    assert "因果候选" not in report
    assert "impulse response" not in report
    assert_report_language(report, "associational_only")


def test_report_uses_structured_confidence_level() -> None:
    module = import_module("research_synthesis.report_builder")
    envelopes = copy.deepcopy(real_envelopes())
    envelopes["estimator"].statuses["confidence_level"] = 0.9
    rows = envelopes["estimator"].statuses["horizon_results"]
    assert isinstance(rows, list)
    for row in rows:
        row["confidence_level"] = 0.9

    report = module.build_report(_inputs(envelopes))

    assert "90% pointwise interval" in report
    assert "95% pointwise interval" not in report
