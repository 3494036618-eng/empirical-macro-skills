from __future__ import annotations

import json
from pathlib import Path

import pytest
from gold_runner import run_gold

GOLD_DIR = Path(__file__).parents[1] / "fixtures" / "gold"
CASES = sorted(GOLD_DIR.glob("rd*"))


def test_exactly_thirty_gold_cases_are_registered() -> None:
    assert [path.name for path in CASES] == [f"rd{number:02d}" for number in range(1, 31)]


@pytest.mark.parametrize("case_dir", CASES, ids=lambda path: path.name)
def test_gold(
    case_dir: Path,
    tmp_path: Path,
    macro_schema_path: Path,
) -> None:
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))

    result = run_gold(case_dir, tmp_path / case_dir.name, macro_schema_path)

    assert result["family"] == expected["expected_family"]
    assert result["claim_eligibility"] == expected["expected_claim_eligibility"]
    assert result["design_readiness"] == expected["expected_readiness"]
    assert set(expected["required_issue_codes"]) <= set(result["issue_codes"])
    assert result["claim_eligibility"] not in expected["forbidden_claim_eligibility"]
