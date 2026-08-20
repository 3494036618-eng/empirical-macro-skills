from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_agent_routing_acceptance.py"


def run_harness(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_dry_run_records_budget_without_model_calls(tmp_path: Path) -> None:
    """Break caught: acceptance starts paid host calls during planning."""
    output = tmp_path / "agent-routing"
    completed = run_harness(
        "--snapshot",
        str(tmp_path / "snapshot"),
        "--output",
        str(output),
        "--dry-run",
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["base_request_count"] == 225
    assert report["worst_case_request_count"] == 450
    assert report["model_calls"] == 0
    assert report["approved"] is False
    assert (output / "budget-plan.json").is_file()


def test_actual_mode_requires_explicit_approval(tmp_path: Path) -> None:
    """Break caught: actual host invocation bypasses the budget gate."""
    completed = run_harness(
        "--snapshot",
        str(tmp_path / "snapshot"),
        "--output",
        str(tmp_path / "agent-routing"),
    )
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "explicit model-call approval required" in completed.stderr


def test_redaction_removes_credentials_and_private_paths() -> None:
    """Break caught: host evidence stores credentials or a developer path."""
    from empirical_macro.agent_acceptance import redact_text

    source = (
        "/" + "Users/example/run "
        + "Bearer "
        + "abcdefghijklmnop "
        + "Authorization:"
        + " abcdefghijklmnop"
    )
    redacted = redact_text(source)
    assert "/" + "Users/" not in redacted
    assert "abcdefghijklmnop" not in redacted
    assert "<redacted>" in redacted


def _intent(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "0.1.0-beta",
        "domain": "empirical_macro",
        "request_kind": "research_idea",
        "method_family": "conditional_dynamic_association",
        "has_research_plan": False,
        "has_macro_data_bundle": False,
        "has_estimator_bundle": False,
        "has_robustness_bundle": False,
        "has_workflow_state": False,
    }
    document.update(overrides)
    return document


def _gold_cases(path: Path) -> None:
    cases = [
        {
            "case_id": "macro-01",
            "category": "vague_research_idea",
            "prompt": "我想研究利率和通胀。",
            "intent": _intent(),
            "state_stage": None,
            "expected_action": "route_research_design",
            "expected_target_skill": "research-design",
            "expected_user_message": None,
        },
        {
            "case_id": "other-01",
            "category": "out_of_scope",
            "prompt": "帮我规划有机合成路线。",
            "intent": _intent(domain="chemistry", method_family=None),
            "state_stage": None,
            "expected_action": "out_of_scope",
            "expected_target_skill": None,
            "expected_user_message": None,
        },
    ]
    path.write_text(
        json.dumps(cases, ensure_ascii=False),
        encoding="utf-8",
    )


def test_prepared_host_requests_do_not_leak_gold_expectations(
    tmp_path: Path,
) -> None:
    """Break caught: host request files reveal the answer key."""
    from empirical_macro.agent_acceptance import prepare_host_requests

    gold = tmp_path / "gold.json"
    _gold_cases(gold)

    report = prepare_host_requests(
        gold_cases_path=gold,
        output_dir=tmp_path / "requests",
        host="trae",
    )

    assert report["request_count"] == 2
    request = json.loads(
        (tmp_path / "requests" / "macro-01.json").read_text(encoding="utf-8")
    )
    assert set(request) == {
        "schema_version",
        "host",
        "case_id",
        "category",
        "prompt",
        "prompt_sha256",
        "workflow_state_stage",
    }
    assert "expected_action" not in request
    assert "intent" not in request


def test_score_host_results_routes_candidate_intents_and_requires_entry_skill(
    tmp_path: Path,
) -> None:
    """Break caught: scoring trusts host-declared actions instead of the Router."""
    from empirical_macro.agent_acceptance import (
        prepare_host_requests,
        score_host_results,
    )

    gold = tmp_path / "gold.json"
    _gold_cases(gold)
    requests = tmp_path / "requests"
    results = tmp_path / "results"
    prepare_host_requests(
        gold_cases_path=gold,
        output_dir=requests,
        host="trae",
    )
    results.mkdir()
    for case_id, triggered_skill, intent in (
        ("macro-01", "empirical-macro", _intent()),
        ("other-01", None, _intent(domain="chemistry", method_family=None)),
    ):
        request = json.loads(
            (requests / f"{case_id}.json").read_text(encoding="utf-8")
        )
        result = {
            "schema_version": "0.1.0-beta",
            "host": "trae",
            "case_id": case_id,
            "prompt_sha256": request["prompt_sha256"],
            "triggered_skill": triggered_skill,
            "candidate_intent": intent,
            "invented_artifact_refs": [],
        }
        (results / f"{case_id}.json").write_text(
            json.dumps(result),
            encoding="utf-8",
        )

    report = score_host_results(
        gold_cases_path=gold,
        results_dir=results,
        host="trae",
    )

    assert report["total"] == 2
    assert report["passed"] == 2
    assert report["wrong_skill_execution"] == 0
    assert report["invented_artifact_ref"] == 0
    case_results = cast(list[dict[str, object]], report["case_results"])
    assert [item["observed_action"] for item in case_results] == [
        "route_research_design",
        "out_of_scope",
    ]


def test_actual_mode_scores_supplied_trae_results(tmp_path: Path) -> None:
    """Break caught: approved execution remains a permanent placeholder."""
    from empirical_macro.agent_acceptance import prepare_host_requests

    gold = tmp_path / "gold.json"
    _gold_cases(gold)
    requests = tmp_path / "requests"
    results = tmp_path / "results"
    prepare_host_requests(
        gold_cases_path=gold,
        output_dir=requests,
        host="trae",
    )
    results.mkdir()
    for case_id, triggered_skill, intent in (
        ("macro-01", "empirical-macro", _intent()),
        ("other-01", None, _intent(domain="chemistry", method_family=None)),
    ):
        request = json.loads(
            (requests / f"{case_id}.json").read_text(encoding="utf-8")
        )
        (results / f"{case_id}.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.1.0-beta",
                    "host": "trae",
                    "case_id": case_id,
                    "prompt_sha256": request["prompt_sha256"],
                    "triggered_skill": triggered_skill,
                    "candidate_intent": intent,
                    "invented_artifact_refs": [],
                }
            ),
            encoding="utf-8",
        )
    output = tmp_path / "agent-routing"

    completed = run_harness(
        "--snapshot",
        str(tmp_path / "snapshot"),
        "--output",
        str(output),
        "--approved",
        "--host",
        "trae",
        "--gold-cases",
        str(gold),
        "--host-results",
        str(results),
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["passed"] == 2
    assert report["status"] == "passed"
    assert (output / "trae-summary.json").is_file()


def test_control_results_require_no_suite_trigger_or_artifact(
    tmp_path: Path,
) -> None:
    """Break caught: no-Skill controls claim suite routing or artifacts."""
    from empirical_macro.agent_acceptance import (
        prepare_control_requests,
        score_control_results,
    )

    gold = tmp_path / "gold.json"
    _gold_cases(gold)
    requests = tmp_path / "control-requests"
    results = tmp_path / "control-results"
    prepare_control_requests(
        gold_cases_path=gold,
        output_dir=requests,
        host="trae",
        count=2,
    )
    results.mkdir()
    for request_path in sorted(requests.glob("*.json")):
        request = json.loads(request_path.read_text(encoding="utf-8"))
        result = {
            "schema_version": "0.1.0-beta",
            "host": "trae",
            "case_id": request["case_id"],
            "prompt_sha256": request["prompt_sha256"],
            "suite_loaded": False,
            "triggered_skill": None,
            "invented_artifact_refs": [],
        }
        (results / request_path.name).write_text(
            json.dumps(result),
            encoding="utf-8",
        )

    report = score_control_results(
        requests_dir=requests,
        results_dir=results,
        host="trae",
    )

    assert report == {
        "schema_version": "0.1.0-beta",
        "host": "trae",
        "status": "passed",
        "total": 2,
        "passed": 2,
        "failed": 0,
        "model_calls": 2,
    }
