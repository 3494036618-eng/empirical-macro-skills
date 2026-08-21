#!/usr/bin/env python3
"""Validate the current Skill structure, contracts, and secret hygiene."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
BEHAVIOR_REPORT = (
    ROOT.parents[1]
    / "03_验收与发布"
    / "robustness-audit"
    / "ra-v1-agent-behavior-2026-08-16"
    / "score-summary.json"
)
REQUIRED_FILES = {
    "SKILL.md",
    "THIRD_PARTY_NOTICES.md",
    "kernel.py",
    "agents/openai.yaml",
    "pyproject.toml",
    "references/adapter-contract.md",
    "references/audit-semantics.md",
    "references/claim-language-policy.md",
    "uv.lock",
    "scripts/compile_audit_plan.py",
    "scripts/quick_validate.py",
    "scripts/run_robustness_audit.py",
    "scripts/validate_bundle.py",
    "src/robustness_audit/contracts.py",
    "src/robustness_audit/pipeline.py",
}
REQUIRED_SCHEMAS = {
    "adapter-capability.schema.json",
    "robustness-audit-plan.schema.json",
    "robustness-audit-request.schema.json",
    "robustness-audit-result.schema.json",
    "robustness-check-result.schema.json",
    "robustness-run-manifest.schema.json",
}
SECRET_PATTERN = re.compile(
    r"ark-[A-Za-z0-9-]{12,}|Authorization\s*:|Bearer\s+[A-Za-z0-9._-]{8,}",
    re.IGNORECASE,
)


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    _, block, _ = text.split("---", 2)
    fields: dict[str, str] = {}
    for line in block.strip().splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip('"')
    return fields


def _secret_findings() -> list[str]:
    excluded = {".venv", ".cache", ".artifacts", "__pycache__"}
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or excluded.intersection(path.parts)
            or path.name == "uv.lock"
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SECRET_PATTERN.search(text):
            findings.append(str(path.relative_to(ROOT)))
    return findings


def _schema_errors(paths: list[Path]) -> list[str]:
    observed = {path.name for path in paths}
    return [
        *(f"missing JSON Schema: {name}" for name in sorted(REQUIRED_SCHEMAS - observed)),
        *(
            f"unexpected JSON Schema: {name}"
            for name in sorted(observed - REQUIRED_SCHEMAS)
        ),
    ]


def _behavior_status() -> str:
    if not BEHAVIOR_REPORT.is_file():
        return "pending"
    try:
        summary = json.loads(BEHAVIOR_REPORT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "invalid_report"
    required = ("codex:skill", "claude:skill", "trae:skill")
    if not all(key in summary for key in required):
        return "pending"
    if all(
        summary.get(key, {}).get("total") == 5
        and summary.get(key, {}).get("passed") == 5
        and summary.get(key, {}).get("schema_valid") == 5
        for key in required
    ):
        return "passed_2026-08-16"
    return "failed"


def main() -> int:
    errors: list[str] = []
    missing = sorted(name for name in REQUIRED_FILES if not (ROOT / name).is_file())
    errors.extend(f"missing required file: {name}" for name in missing)
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = _frontmatter(skill_text)
    expected_fields = ["compatibility", "description", "license", "name"]
    if sorted(frontmatter) != expected_fields:
        errors.append("SKILL frontmatter fields are invalid")
    if frontmatter.get("name") != "robustness-audit":
        errors.append("SKILL name must be robustness-audit")
    if frontmatter.get("license") != "Apache-2.0":
        errors.append("SKILL license must be Apache-2.0")
    if "Python 3.12" not in frontmatter.get("compatibility", ""):
        errors.append("SKILL compatibility must name Python 3.12")
    description = frontmatter.get("description", "")
    if not description.startswith("Use when ") or len(description) > 200:
        errors.append("SKILL description must be a concise Use when trigger")
    schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
    for path in schemas:
        Draft202012Validator.check_schema(
            json.loads(path.read_text(encoding="utf-8"))
        )
    errors.extend(_schema_errors(schemas))
    secret_findings = _secret_findings()
    errors.extend(f"secret-like value: {name}" for name in secret_findings)
    agent_text = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if not all(
        token in agent_text
        for token in ("interface:", "display_name:", "default_prompt:")
    ):
        errors.append("agents/openai.yaml is missing required interface metadata")
    behavior_status = _behavior_status()
    if behavior_status in {"invalid_report", "failed"}:
        errors.append(f"behavior pressure tests: {behavior_status}")
    report = {
        "valid": not errors,
        "schema_count": len(schemas),
        "missing_files": missing,
        "secret_findings": secret_findings,
        "behavior_pressure_tests": behavior_status,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
