#!/usr/bin/env python3
"""Run fast, offline structure checks for the empirical-macro Skill."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from empirical_macro.contracts import SCHEMA_FILES, load_schema

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "SKILL.md",
    "THIRD_PARTY_NOTICES.md",
    "agents/openai.yaml",
    "configs/capability-registry.json",
    "configs/skill-suite.json",
    "references/routing-policy.md",
    "references/supported-scope.md",
    "references/artifact-handoffs.md",
)
FORBIDDEN_IMPORTS = {
    "macro_data",
    "research_design",
    "time_series_dynamics",
    "robustness_audit",
    "research_synthesis",
}


def _frontmatter() -> dict[str, str]:
    lines = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("skill_frontmatter_missing")
    end = lines.index("---", 1)
    document: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError("skill_frontmatter_invalid")
        document[key.strip()] = value.strip().strip('"')
    return document


def _required_findings() -> list[str]:
    findings = [f"required_file_missing:{name}" for name in REQUIRED if not (ROOT / name).is_file()]
    try:
        frontmatter = _frontmatter()
    except (OSError, ValueError) as error:
        return [*findings, str(error)]
    if set(frontmatter) != {"name", "description"}:
        findings.append("skill_frontmatter_fields_invalid")
    if frontmatter.get("name") != "empirical-macro":
        findings.append("skill_name_invalid")
    description = frontmatter.get("description", "")
    if len(description) > 200 or "Invoke" not in description:
        findings.append("skill_description_invalid")
    return findings


def _schema_findings() -> list[str]:
    findings: list[str] = []
    for contract in SCHEMA_FILES:
        try:
            schema = load_schema(contract)
            Draft202012Validator.check_schema(schema)
        except (OSError, ValueError) as error:
            findings.append(f"schema_invalid:{contract}:{error}")
    return findings


def _complexity(node: ast.AST) -> int:
    branches = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match)
    return 1 + sum(isinstance(child, branches) for child in ast.walk(node))


def _source_findings() -> tuple[list[str], dict[str, int]]:
    findings: list[str] = []
    metrics = {"production_files": 0, "max_file_lines": 0, "max_function_lines": 0}
    paths = sorted((ROOT / "src" / "empirical_macro").glob("*.py")) + sorted(
        (ROOT / "scripts").glob("*.py")
    )
    private_prefixes = ("/" + "Users/", "/" + "home/", "/" + "private/var/")
    for path in paths:
        metrics["production_files"] += 1
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        metrics["max_file_lines"] = max(metrics["max_file_lines"], len(lines))
        if len(lines) >= 400:
            findings.append(f"production_file_too_long:{path.name}")
        if any(prefix in text for prefix in private_prefixes):
            findings.append(f"private_path_found:{path.name}")
        tree = ast.parse(text, filename=str(path))
        findings.extend(_ast_findings(path, tree, metrics))
    return findings, metrics


def _ast_findings(
    path: Path,
    tree: ast.Module,
    metrics: dict[str, int],
) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno or node.lineno
            length = end - node.lineno + 1
            metrics["max_function_lines"] = max(metrics["max_function_lines"], length)
            if length >= 80:
                findings.append(f"production_function_too_long:{path.name}:{node.name}")
            if _complexity(node) > 10:
                findings.append(f"complexity_exceeded:{path.name}:{node.name}")
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".")[0] for alias in node.names}
            if roots & FORBIDDEN_IMPORTS:
                findings.append(f"private_import:{path.name}")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_IMPORTS:
                findings.append(f"private_import:{path.name}")
    return findings


def main() -> int:
    source_findings, metrics = _source_findings()
    findings = [*_required_findings(), *_schema_findings(), *source_findings]
    report = {
        "valid": not findings,
        "issue_codes": sorted(set(findings)),
        "schema_count": len(SCHEMA_FILES),
        **metrics,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
