#!/usr/bin/env python3
"""快速验证 Skill 结构、合同和正式 research package。"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from research_synthesis.contracts import SCHEMA_FILES, load_schema
from research_synthesis.exporter import (
    PERSONAL_PATH_PATTERN,
    SECRET_PATTERN,
    validate_bundle,
)

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "SKILL.md",
    "THIRD_PARTY_NOTICES.md",
    "kernel.py",
    "configs/local-upstream-adapters.json",
    "scripts/quick_validate.py",
    "scripts/run_research_synthesis.py",
    "scripts/validate_bundle.py",
    "src/research_synthesis/pipeline.py",
    "src/research_synthesis/report_builder.py",
    "references/report-contract.md",
    "references/claim-language-policy.md",
    "references/reproduction-package.md",
    "pyproject.toml",
    "uv.lock",
}
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
    findings: list[str] = []
    excluded = {
        ".venv",
        ".cache",
        ".artifacts",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or excluded.intersection(path.parts)
            or path.name in {"uv.lock", ".coverage"}
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SECRET_PATTERN.search(text) or PERSONAL_PATH_PATTERN.search(text):
            findings.append(str(path.relative_to(ROOT)))
    return findings


def main() -> int:
    errors: list[str] = []
    missing = sorted(name for name in REQUIRED if not (ROOT / name).is_file())
    errors.extend(f"缺少必要文件: {name}" for name in missing)
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = _frontmatter(skill)
    expected_fields = ["compatibility", "description", "license", "name"]
    if sorted(frontmatter) != expected_fields:
        errors.append("SKILL.md frontmatter 字段无效")
    if frontmatter.get("name") != "research-synthesis":
        errors.append("SKILL.md name 必须为 research-synthesis")
    if frontmatter.get("license") != "Apache-2.0":
        errors.append("SKILL.md license 必须为 Apache-2.0")
    if "Python 3.12" not in frontmatter.get("compatibility", ""):
        errors.append("SKILL.md compatibility 必须声明 Python 3.12")
    for contract in SCHEMA_FILES:
        Draft202012Validator.check_schema(load_schema(contract))
    findings = _secret_findings()
    errors.extend(f"疑似凭证: {name}" for name in findings)
    artifact = ROOT / ".artifacts" / "jel-example5-research-package"
    artifact_result: dict[str, object] | str = (
        validate_bundle(artifact) if artifact.exists() else "pending"
    )
    if isinstance(artifact_result, dict) and artifact_result["valid"] is not True:
        errors.append(f"正式 Artifact 无效: {artifact_result['errors']}")
    report = {
        "valid": not errors,
        "schema_count": len(SCHEMA_FILES),
        "primary_output": "research-report.md",
        "skill_lines": len(skill.splitlines()),
        "missing_files": missing,
        "secret_findings": findings,
        "artifact": artifact_result,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
