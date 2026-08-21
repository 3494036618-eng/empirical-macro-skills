#!/usr/bin/env python3
"""Validate research-design Skill structure, schemas, metadata, and secrets."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from research_design.exporter import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
BEHAVIOR_REPORT = (
    ROOT.parents[1]
    / "03_验收与发布"
    / "research-design"
    / "rd-4-agent-behavior-2026-08-16"
    / "score-summary.json"
)
REQUIRED = [
    "SKILL.md",
    "THIRD_PARTY_NOTICES.md",
    "kernel.py",
    "agents/openai.yaml",
    "scripts/quick_validate.py",
    "scripts/materialize_execution_ready_bundle.py",
    "scripts/run_research_design.py",
    "scripts/validate_bundle.py",
    "src/research_design/execution_ready_bundle.py",
    "src/research_design/contracts.py",
    "src/research_design/pipeline.py",
    "src/research_design/policy_gate.py",
    "references/research-taxonomy.md",
    "references/design-cards.md",
    "references/identification-assumptions.md",
    "references/forecasting-design.md",
    "references/expert-review-policy.md",
    "pyproject.toml",
]
SECRET_PATTERN = re.compile(
    r"ark-[A-Za-z0-9-]{12,}|Authorization\s*:|Bearer\s+[A-Za-z0-9._-]{8,}",
    re.IGNORECASE,
)
REQUIRED_SCHEMAS = {
    "data-requirements.schema.json",
    "identification-audit.schema.json",
    "research-design-request.schema.json",
    "research-design-run-manifest.schema.json",
    "research-intake.schema.json",
    "research-plan.schema.json",
    "robustness-handoff.schema.json",
}


def _frontmatter(skill_text: str) -> dict[str, str]:
    if not skill_text.startswith("---\n"):
        return {}
    _, block, _ = skill_text.split("---", 2)
    result: dict[str, str] = {}
    for line in block.strip().splitlines():
        key, separator, value = line.partition(":")
        if separator:
            result[key.strip()] = value.strip().strip('"')
    return result


def _secret_findings() -> list[str]:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or ".venv" in path.parts
            or "__pycache__" in path.parts
            or path.name == "uv.lock"
        ):
            continue
        if SECRET_PATTERN.search(path.read_text(encoding="utf-8", errors="ignore")):
            findings.append(str(path.relative_to(ROOT)))
    return findings


def _behavior_status() -> str:
    if not BEHAVIOR_REPORT.is_file():
        return "pending"
    try:
        summary = json.loads(BEHAVIOR_REPORT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "invalid_report"
    required = ("codex:skill", "claude:skill", "trae:skill")
    if all(
        summary.get(key, {}).get("total") == 5
        and summary.get(key, {}).get("passed") == 5
        and summary.get(key, {}).get("schema_valid") == 5
        for key in required
    ):
        return "passed_2026-08-16"
    return "failed"


def _schema_inventory_errors(paths: list[Path]) -> list[str]:
    observed = {path.name for path in paths}
    return [
        *(f"missing JSON Schema: {name}" for name in sorted(REQUIRED_SCHEMAS - observed)),
        *(
            f"unexpected JSON Schema: {name}"
            for name in sorted(observed - REQUIRED_SCHEMAS)
        ),
    ]


def main() -> int:
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = _frontmatter(skill_text)
    errors: list[str] = []
    expected_fields = ["compatibility", "description", "license", "name"]
    if sorted(frontmatter) != expected_fields:
        errors.append("SKILL.md frontmatter fields are invalid")
    if frontmatter.get("name") != "research-design":
        errors.append("SKILL.md name must be research-design")
    if frontmatter.get("license") != "Apache-2.0":
        errors.append("SKILL.md license must be Apache-2.0")
    if "Python 3.12" not in frontmatter.get("compatibility", ""):
        errors.append("SKILL.md compatibility must name Python 3.12")
    description = frontmatter.get("description", "")
    if not description or len(description) > 200:
        errors.append("SKILL.md description must be present and at most 200 characters")
    if len(skill_text.splitlines()) > 500:
        errors.append("SKILL.md exceeds 500 lines")
    errors.extend(f"missing required file: {name}" for name in missing)

    schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
    for path in schemas:
        Draft202012Validator.check_schema(
            json.loads(path.read_text(encoding="utf-8"))
        )
    errors.extend(_schema_inventory_errors(schemas))

    agent_text = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    required_metadata = ("interface:", "display_name:", "default_prompt:")
    if not all(token in agent_text for token in required_metadata):
        errors.append("agents/openai.yaml is missing required interface metadata")

    secret_findings = _secret_findings()
    errors.extend(f"secret-like value: {name}" for name in secret_findings)
    behavior_status = _behavior_status()
    if behavior_status in {"invalid_report", "failed"}:
        errors.append(f"behavior pressure tests: {behavior_status}")
    public_bundle = ROOT / "fixtures" / "public" / "jel-example5-design"
    execution_ready_validation = validate_bundle(
        public_bundle
        if public_bundle.exists()
        else ROOT / ".artifacts" / "jel-example5-design"
    )
    if execution_ready_validation["valid"] is not True:
        errors.append(
            "execution-ready bundle invalid: "
            f"{execution_ready_validation['errors']}"
        )
    report = {
        "valid": not errors,
        "frontmatter_keys": sorted(frontmatter),
        "skill_lines": len(skill_text.splitlines()),
        "schema_count": len(schemas),
        "missing_files": missing,
        "secret_findings": secret_findings,
        "behavior_pressure_tests": behavior_status,
        "execution_ready_bundle_valid": (
            execution_ready_validation["valid"] is True
        ),
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
