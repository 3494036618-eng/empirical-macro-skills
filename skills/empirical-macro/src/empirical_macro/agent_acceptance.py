from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from empirical_macro.contracts import validate_document
from empirical_macro.models import ResearchIntent
from empirical_macro.router import route_intent

HOSTS = ("trae", "codex", "claude-code")
ROUTING_CASES_PER_HOST = 65
CONTROL_CASES_PER_HOST = 10
MAXIMUM_RETRIES = 1
PRIVATE_PATTERN = re.compile(
    r"(?:/" + r"Users|/home|/private/var)/[^\s\"']+"
)
SECRET_PATTERN = re.compile(
    r"(?:Bearer[ \t]+|Authorization:[ \t]*|"
    r"X-Agent-Plan-Key[ \t]*[:=][ \t]*)[A-Za-z0-9._-]{8,}",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _StateView:
    current_stage: str


def redact_text(value: str) -> str:
    redacted = PRIVATE_PATTERN.sub("<redacted>", value)
    return SECRET_PATTERN.sub("<redacted>", redacted)


def host_availability() -> dict[str, dict[str, object]]:
    return {
        "trae": {
            "execution_mode": "current_host_or_authorized_subagent",
            "cli": None,
            "available": True,
        },
        "codex": {
            "execution_mode": "cli",
            "cli": shutil.which("codex"),
            "available": shutil.which("codex") is not None,
        },
        "claude-code": {
            "execution_mode": "cli",
            "cli": shutil.which("claude"),
            "available": shutil.which("claude") is not None,
        },
    }


def build_budget_plan(snapshot: Path) -> dict[str, object]:
    per_host = ROUTING_CASES_PER_HOST + CONTROL_CASES_PER_HOST
    base = per_host * len(HOSTS)
    return {
        "schema_version": "0.1.0-beta",
        "snapshot": snapshot.name,
        "hosts": list(HOSTS),
        "routing_cases_per_host": ROUTING_CASES_PER_HOST,
        "control_cases_per_host": CONTROL_CASES_PER_HOST,
        "requests_per_host": per_host,
        "base_request_count": base,
        "maximum_retries": MAXIMUM_RETRIES,
        "worst_case_request_count": base * (MAXIMUM_RETRIES + 1),
        "models": {host: "pending_configuration" for host in HOSTS},
        "credential_source": "host_managed_not_recorded",
        "cost_boundary": "requires_explicit_model_call_approval",
        "approved": False,
        "model_calls": 0,
        "availability": host_availability(),
    }


def write_budget_plan(
    *,
    snapshot: Path,
    output_dir: Path,
) -> dict[str, object]:
    plan = build_budget_plan(snapshot)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "budget-plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return plan


def _load_array(path: Path) -> list[dict[str, object]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, list) or any(
        not isinstance(item, dict) for item in document
    ):
        raise ValueError(f"{path.name} must contain an object array")
    return cast(list[dict[str, object]], document)


def _load_object(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.name} must contain an object")
    return cast(dict[str, object], document)


def _prompt_sha256(prompt: str) -> str:
    return "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _write_json(path: Path, document: object) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def prepare_host_requests(
    *,
    gold_cases_path: Path,
    output_dir: Path,
    host: str,
) -> dict[str, object]:
    if host not in HOSTS:
        raise ValueError(f"unsupported host: {host}")
    cases = _load_array(gold_cases_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        case_id = str(case["case_id"])
        prompt = str(case["prompt"])
        request = {
            "schema_version": "0.1.0-beta",
            "host": host,
            "case_id": case_id,
            "category": case["category"],
            "prompt": prompt,
            "prompt_sha256": _prompt_sha256(prompt),
            "workflow_state_stage": case.get("state_stage"),
        }
        _write_json(output_dir / f"{case_id}.json", request)
    return {
        "host": host,
        "request_count": len(cases),
        "output_dir": str(output_dir),
    }


def _intent(document: dict[str, object]) -> ResearchIntent:
    validate_document("research_intent", document)
    return ResearchIntent(
        domain=cast(str, document["domain"]),
        request_kind=cast(str, document["request_kind"]),
        method_family=cast(str | None, document["method_family"]),
        has_research_plan=cast(bool, document["has_research_plan"]),
        has_macro_data_bundle=cast(bool, document["has_macro_data_bundle"]),
        has_estimator_bundle=cast(bool, document["has_estimator_bundle"]),
        has_robustness_bundle=cast(bool, document["has_robustness_bundle"]),
        has_workflow_state=cast(bool, document["has_workflow_state"]),
    )


def _score_case(
    case: dict[str, object],
    result_path: Path,
    host: str,
) -> dict[str, object]:
    issues: list[str] = []
    observed_action: str | None = None
    observed_target: str | None = None
    observed_message: str | None = None
    try:
        result = _load_object(result_path)
        prompt = str(case["prompt"])
        if result.get("host") != host or result.get("case_id") != case["case_id"]:
            issues.append("host_result_identity_mismatch")
        if result.get("prompt_sha256") != _prompt_sha256(prompt):
            issues.append("prompt_binding_mismatch")
        expected_entry = (
            None if case["expected_action"] == "out_of_scope" else "empirical-macro"
        )
        if result.get("triggered_skill") != expected_entry:
            issues.append("wrong_entry_skill")
        if result.get("invented_artifact_refs") != []:
            issues.append("invented_artifact_ref")
        candidate = result.get("candidate_intent")
        if not isinstance(candidate, dict):
            issues.append("candidate_intent_missing")
        else:
            state_stage = case.get("state_stage")
            state = _StateView(str(state_stage)) if state_stage is not None else None
            decision = route_intent(_intent(candidate), state)
            observed_action = decision.action
            observed_target = decision.target_skill
            observed_message = decision.user_message
            expected = (
                case["expected_action"],
                case["expected_target_skill"],
                case["expected_user_message"],
            )
            observed = (observed_action, observed_target, observed_message)
            if observed != expected:
                issues.append("route_mismatch")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        issues.append("host_result_invalid")
    return {
        "case_id": case["case_id"],
        "passed": not issues,
        "issue_codes": sorted(set(issues)),
        "observed_action": observed_action,
        "observed_target_skill": observed_target,
        "observed_user_message": observed_message,
    }


def score_host_results(
    *,
    gold_cases_path: Path,
    results_dir: Path,
    host: str,
) -> dict[str, object]:
    if host not in HOSTS:
        raise ValueError(f"unsupported host: {host}")
    cases = _load_array(gold_cases_path)
    case_results = [
        _score_case(case, results_dir / f"{case['case_id']}.json", host)
        for case in cases
    ]
    passed = sum(result["passed"] is True for result in case_results)
    wrong_skill = sum(
        "wrong_entry_skill" in cast(list[str], result["issue_codes"])
        for result in case_results
    )
    invented = sum(
        "invented_artifact_ref" in cast(list[str], result["issue_codes"])
        for result in case_results
    )
    return {
        "schema_version": "0.1.0-beta",
        "host": host,
        "status": "passed" if passed == len(cases) else "failed",
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "wrong_skill_execution": wrong_skill,
        "invented_artifact_ref": invented,
        "model_calls": len(cases),
        "case_results": case_results,
    }


def prepare_control_requests(
    *,
    gold_cases_path: Path,
    output_dir: Path,
    host: str,
    count: int,
) -> dict[str, object]:
    if host not in HOSTS:
        raise ValueError(f"unsupported host: {host}")
    if count < 1:
        raise ValueError("control count must be positive")
    cases = _load_array(gold_cases_path)[:count]
    output_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        prompt = str(case["prompt"])
        request = {
            "schema_version": "0.1.0-beta",
            "host": host,
            "case_id": case["case_id"],
            "category": case["category"],
            "prompt": prompt,
            "prompt_sha256": _prompt_sha256(prompt),
            "suite_loaded": False,
        }
        _write_json(output_dir / f"{case['case_id']}.json", request)
    return {
        "host": host,
        "request_count": len(cases),
        "output_dir": str(output_dir),
    }


def _control_passes(
    request: dict[str, object],
    result: dict[str, object],
    host: str,
) -> bool:
    return (
        result.get("schema_version") == "0.1.0-beta"
        and result.get("host") == host
        and result.get("case_id") == request.get("case_id")
        and result.get("prompt_sha256") == request.get("prompt_sha256")
        and result.get("suite_loaded") is False
        and result.get("triggered_skill") is None
        and result.get("invented_artifact_refs") == []
    )


def score_control_results(
    *,
    requests_dir: Path,
    results_dir: Path,
    host: str,
) -> dict[str, object]:
    if host not in HOSTS:
        raise ValueError(f"unsupported host: {host}")
    requests = [_load_object(path) for path in sorted(requests_dir.glob("*.json"))]
    passed = 0
    for request in requests:
        try:
            result = _load_object(
                results_dir / f"{request['case_id']}.json"
            )
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        passed += _control_passes(request, result, host)
    return {
        "schema_version": "0.1.0-beta",
        "host": host,
        "status": "passed" if passed == len(requests) else "failed",
        "total": len(requests),
        "passed": passed,
        "failed": len(requests) - passed,
        "model_calls": len(requests),
    }
