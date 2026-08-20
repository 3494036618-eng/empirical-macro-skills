#!/usr/bin/env python3
"""Validate Skill structure, contracts, generated bundles, and secrets."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from time_series_dynamics.exporter import validate_bundle
from time_series_dynamics.input_evidence import validate_input_evidence

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "SKILL.md",
    "THIRD_PARTY_NOTICES.md",
    "agents/openai.yaml",
    "scripts/fetch_jel_example5.py",
    "scripts/materialize_input_evidence.py",
    "scripts/run_time_series_dynamics.py",
    "scripts/validate_bundle.py",
    "scripts/validate_input_evidence.py",
    "src/time_series_dynamics/contracts.py",
    "src/time_series_dynamics/horizon_regression.py",
    "src/time_series_dynamics/input_evidence.py",
    "src/time_series_dynamics/claim_policy.py",
    "src/time_series_dynamics/pipeline.py",
    "references/analysis-tracks.md",
    "references/claim-language-policy.md",
    "references/jorda-taylor-example5.md",
    "tests/test_jel_replication.py",
    "tests/test_input_evidence.py",
    "pyproject.toml",
    "uv.lock",
]
SECRET_PATTERN = re.compile(
    r"ark-[A-Za-z0-9-]{12,}|Authorization\s*:|Bearer\s+[A-Za-z0-9._-]{8,}",
    re.IGNORECASE,
)
REQUIRED_SCHEMAS = {
    "macro-data-handoff.schema.json",
    "research-plan-handoff.schema.json",
    "shock-identification-artifact.schema.json",
    "time-series-diagnostics.schema.json",
    "time-series-dynamics-request.schema.json",
    "time-series-dynamics-result.schema.json",
    "time-series-input-evidence-manifest.schema.json",
    "time-series-run-manifest.schema.json",
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
    excluded = {".venv", ".cache", ".artifacts", "__pycache__"}
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


def _schema_inventory_errors(paths: list[Path]) -> list[str]:
    observed = {path.name for path in paths}
    missing = sorted(REQUIRED_SCHEMAS - observed)
    unexpected = sorted(observed - REQUIRED_SCHEMAS)
    return [
        *(f"missing JSON Schema: {name}" for name in missing),
        *(f"unexpected JSON Schema: {name}" for name in unexpected),
    ]


def main() -> int:
    errors: list[str] = []
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    errors.extend(f"missing required file: {name}" for name in missing)
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = _frontmatter(skill)
    if sorted(frontmatter) != ["description", "name"]:
        errors.append("SKILL frontmatter must contain only name and description")
    if frontmatter.get("name") != "time-series-dynamics":
        errors.append("SKILL name must be time-series-dynamics")
    schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
    for path in schemas:
        Draft202012Validator.check_schema(
            json.loads(path.read_text(encoding="utf-8"))
        )
    errors.extend(_schema_inventory_errors(schemas))
    bundles: dict[str, object] = {}
    for name in ("jel-example5-causal", "jel-example5-association"):
        path = ROOT / ".artifacts" / name
        bundles[name] = validate_bundle(path) if path.exists() else "pending"
    input_evidence_path = ROOT / ".artifacts" / "jel-example5-input-evidence"
    if not input_evidence_path.exists():
        input_evidence = {
            "valid": False,
            "errors": ["input evidence bundle is pending"],
        }
        errors.append("input evidence bundle is pending")
    else:
        input_evidence = validate_input_evidence(input_evidence_path)
    if input_evidence_path.exists() and input_evidence["valid"] is not True:
        errors.append(f"input evidence bundle invalid: {input_evidence['errors']}")
    secret_findings = _secret_findings()
    errors.extend(f"secret-like value: {name}" for name in secret_findings)
    report = {
        "valid": not errors,
        "schema_count": len(schemas),
        "skill_lines": len(skill.splitlines()),
        "missing_files": missing,
        "secret_findings": secret_findings,
        "bundles": bundles,
        "input_evidence": input_evidence,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
