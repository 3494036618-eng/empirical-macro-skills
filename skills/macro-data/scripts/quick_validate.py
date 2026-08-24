"""Quick structural and secret validation for the macro-data Skill."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "SKILL.md",
    "THIRD_PARTY_NOTICES.md",
    "kernel.py",
    "agents/openai.yaml",
    "scripts/import_public_research_artifact.py",
    "scripts/probe_datapro.py",
    "scripts/quick_validate.py",
    "scripts/run_datapro_first.py",
    "scripts/run_macro_data.py",
    "scripts/validate_bundle.py",
    "src/macro_data/contracts.py",
    "src/macro_data/completion_assembler.py",
    "src/macro_data/completion_export.py",
    "src/macro_data/completion_integrity.py",
    "src/macro_data/completion_validation.py",
    "src/macro_data/bundle_export.py",
    "src/macro_data/bundle_validation.py",
    "src/macro_data/models.py",
    "src/macro_data/request_loader.py",
    "src/macro_data/request_parser.py",
    "src/macro_data/result_parser.py",
    "src/macro_data/semantic_conflicts.py",
    "src/macro_data/semantic_constraints.py",
    "src/macro_data/semantic_coverage.py",
    "src/macro_data/semantic_identity.py",
    "src/macro_data/semantic_readiness.py",
    "src/macro_data/semantic_validator.py",
    "src/macro_data/series_mapping.py",
    "src/macro_data/normalizer.py",
    "src/macro_data/openai4s_datapro.py",
    "src/macro_data/observation_matrix.py",
    "src/macro_data/primary_cell_ledger.py",
    "src/macro_data/provenance.py",
    "src/macro_data/public_artifact_import.py",
    "src/macro_data/request_migration.py",
    "src/macro_data/residual_gap.py",
    "src/macro_data/result_builder.py",
    "src/macro_data/result_builder_v3.py",
    "src/macro_data/exporter.py",
    "src/macro_data/pipeline.py",
    "src/macro_data/metadata_gate.py",
    "src/macro_data/transformation_engine.py",
    "src/macro_data/connectors/base.py",
    "src/macro_data/connectors/datapro.py",
    "src/macro_data/connectors/world_bank.py",
    "src/macro_data/source_registry.py",
    "src/macro_data/source_router.py",
    "src/macro_data/multi_source_pipeline.py",
    "references/datapro-contract.md",
    "references/world-bank-contract.md",
    "references/research-readiness.md",
    "references/indicator-identity.md",
    "references/source-policy.md",
    "pyproject.toml",
]
SECRET_PATTERN = re.compile(
    r"ark-[A-Za-z0-9-]{12,}|"
    r"(?<![A-Za-z0-9_])Authorization\s*:|"
    r"Bearer\s+[A-Za-z0-9._-]{8,}",
    re.IGNORECASE,
)
REQUIRED_SCHEMA_FILES = {
    "completion-manifest.schema.json",
    "expected-observation-matrix.schema.json",
    "macro-data-request-v0.3.schema.json",
    "macro-data-request.schema.json",
    "macro-data-result-v0.3.schema.json",
    "macro-data-result.schema.json",
    "provenance.schema.json",
    "public-research-artifact.schema.json",
    "residual-gap-manifest.schema.json",
    "run-manifest.schema.json",
    "series-specification.schema.json",
}


def _frontmatter(skill_text: str) -> dict[str, str]:
    if not skill_text.startswith("---\n"):
        return {}
    _, block, _ = skill_text.split("---", 2)
    result = {}
    for line in block.strip().splitlines():
        key, separator, value = line.partition(":")
        if separator:
            result[key.strip()] = value.strip().strip('"')
    return result


def _structure_findings() -> tuple[list[str], str, dict[str, str], list[str]]:
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = _frontmatter(skill_text)
    errors: list[str] = []
    expected_fields = ["compatibility", "description", "license", "name"]
    if sorted(frontmatter) != expected_fields:
        errors.append("SKILL.md frontmatter fields are invalid")
    if frontmatter.get("name") != "macro-data":
        errors.append("SKILL.md name must be macro-data")
    if frontmatter.get("license") != "Apache-2.0":
        errors.append("SKILL.md license must be Apache-2.0")
    if "Python 3.12" not in frontmatter.get("compatibility", ""):
        errors.append("SKILL.md compatibility must name Python 3.12")
    if not frontmatter.get("description") or len(frontmatter["description"]) > 200:
        errors.append("SKILL.md description must be present and at most 200 characters")
    if len(skill_text.splitlines()) > 500:
        errors.append("SKILL.md exceeds 500 lines")
    errors.extend(f"missing required file: {name}" for name in missing)
    return missing, skill_text, frontmatter, errors


def _schema_findings() -> tuple[int, list[str]]:
    schema_files = sorted((ROOT / "schemas").glob("*.schema.json"))
    for path in schema_files:
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))
    actual = {path.name for path in schema_files}
    missing = sorted(REQUIRED_SCHEMA_FILES - actual)
    unexpected = sorted(actual - REQUIRED_SCHEMA_FILES)
    errors = [f"missing required JSON Schema: {name}" for name in missing]
    errors.extend(f"unexpected JSON Schema: {name}" for name in unexpected)
    return len(schema_files), errors


def _agent_findings() -> list[str]:
    agent_text = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if not all(token in agent_text for token in ("interface:", "display_name:", "default_prompt:")):
        return ["agents/openai.yaml is missing required interface metadata"]
    return []


def _secret_findings() -> list[str]:
    secret_findings = []
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or ".venv" in path.parts
            or "__pycache__" in path.parts
            or path.name == "uv.lock"
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SECRET_PATTERN.search(text):
            secret_findings.append(str(path.relative_to(ROOT)))
    return secret_findings


def main() -> int:
    missing, skill_text, frontmatter, errors = _structure_findings()
    schema_count, schema_errors = _schema_findings()
    errors.extend(schema_errors)
    errors.extend(_agent_findings())
    secret_findings = _secret_findings()
    errors.extend(f"secret-like value: {name}" for name in secret_findings)
    report = {
        "valid": not errors,
        "frontmatter_keys": sorted(frontmatter),
        "skill_lines": len(skill_text.splitlines()),
        "schema_count": schema_count,
        "missing_files": missing,
        "secret_findings": secret_findings,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
