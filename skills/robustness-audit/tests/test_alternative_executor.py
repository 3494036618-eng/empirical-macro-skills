from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from robustness_audit.alternative_executor import execute_alternatives
from robustness_audit.models import AuditPlan
from robustness_audit.plan_compiler import compile_audit_plan
from robustness_audit.subprocess_runner import CommandResult

ROOT = Path(__file__).resolve().parents[1]
TIME_SERIES_ROOT = ROOT.parent / "time-series-dynamics"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _plan(count: int = 3) -> AuditPlan:
    document = compile_audit_plan(
        _load(ROOT / "fixtures" / "synthetic" / "audit-request.json"),
        _load(ROOT / "fixtures" / "external" / "jel-example5.robustness-handoff.json"),
        _load(
            TIME_SERIES_ROOT / "fixtures" / "synthetic" / "jel.causal.request.json"
        ),
        _load(ROOT / "fixtures" / "synthetic" / "adapter-capability.json"),
    )
    plan = AuditPlan.from_document(document)
    return replace(
        plan,
        alternatives=plan.alternatives[:count],
        max_variants=count + 1,
    )


def _baseline() -> dict[str, object]:
    return _load(
        TIME_SERIES_ROOT / "fixtures" / "synthetic" / "jel.causal.request.json"
    )


class FakeAdapter:
    def __init__(self, behaviors: list[str]) -> None:
        self.behaviors = behaviors
        self.calls = 0

    def derive_request(
        self,
        baseline: dict[str, object],
        patch: dict[str, object],
        alternative_id: str,
    ) -> dict[str, object]:
        return {
            **baseline,
            **patch,
            "request_id": "tsd-request-" + alternative_id.removeprefix("ra-alt-"),
        }

    def execute(
        self,
        request_path: Path,
        input_paths: dict[str, Path],
        output_dir: Path,
        timeout_seconds: float,
    ) -> CommandResult:
        del input_paths, timeout_seconds
        behavior = self.behaviors[self.calls]
        self.calls += 1
        if behavior == "timeout":
            raise subprocess.TimeoutExpired(["fake"], 0.1)
        output_dir.mkdir(parents=True)
        request = _load(request_path)
        if behavior == "error":
            return CommandResult(1, "", "declared failure", 0.1)
        (output_dir / "result.json").write_text(
            json.dumps(
                {
                    "result_id": "tsd-result-" + str(request["request_id"])[12:],
                    "request_id": (
                        "tsd-request-ffffffffffffffff"
                        if behavior == "misbound"
                        else request["request_id"]
                    ),
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "request.json").write_text(
            json.dumps(request),
            encoding="utf-8",
        )
        for filename in ("diagnostics.json", "run-manifest.json"):
            (output_dir / filename).write_text(
                json.dumps({"request_id": request["request_id"]}),
                encoding="utf-8",
            )
        if behavior == "invalid":
            (output_dir / "invalid.marker").write_text("invalid", encoding="utf-8")
        return CommandResult(0, "{}", "", 0.1)

    def validate_result_bundle(self, output_dir: Path) -> None:
        if (output_dir / "invalid.marker").exists():
            raise ValueError("invalid bundle")


class ReusingRequestAdapter(FakeAdapter):
    def derive_request(
        self,
        baseline: dict[str, object],
        patch: dict[str, object],
        alternative_id: str,
    ) -> dict[str, object]:
        del alternative_id
        return {
            **baseline,
            **patch,
            "request_id": "tsd-request-0000000000000000",
        }


def test_executor_preserves_order_and_failed_records(tmp_path: Path) -> None:
    plan = _plan()
    adapter = FakeAdapter(["success", "error", "success"])

    records = execute_alternatives(
        plan,
        adapter,
        _baseline(),
        {},
        tmp_path,
    )

    expected_ids = [item.alternative_id for item in plan.alternatives]
    assert [item["alternative_id"] for item in records] == expected_ids
    assert [item["status"] for item in records] == ["success", "error", "success"]
    assert records[1]["execution_error"] == "declared failure"
    assert records[1]["returncode"] == 1
    assert records[1]["stderr"] == "declared failure"
    assert (tmp_path / "alternative-bundles" / expected_ids[2]).is_dir()


@pytest.mark.parametrize(
    ("behavior", "issue"),
    [
        ("timeout", "alternative_timeout"),
        ("invalid", "alternative_bundle_invalid"),
        ("misbound", "alternative_bundle_request_mismatch"),
    ],
)
def test_executor_records_timeout_and_invalid_bundle(
    behavior: str,
    issue: str,
    tmp_path: Path,
) -> None:
    plan = _plan(1)

    records = execute_alternatives(
        plan,
        FakeAdapter([behavior]),
        _baseline(),
        {},
        tmp_path,
    )

    assert records[0]["status"] == "error"
    assert records[0]["issue_codes"] == [issue]


def test_executor_rejects_variant_budget_mismatch(tmp_path: Path) -> None:
    plan = replace(_plan(), max_variants=3)

    with pytest.raises(ValueError, match="variant_budget_exceeded"):
        execute_alternatives(
            plan,
            FakeAdapter(["success", "success", "success"]),
            _baseline(),
            {},
            tmp_path,
        )


def test_executor_rejects_alternative_request_id_reuse(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="alternative_request_id_reuse"):
        execute_alternatives(
            _plan(2),
            ReusingRequestAdapter(["success", "success"]),
            _baseline(),
            {},
            tmp_path,
        )
