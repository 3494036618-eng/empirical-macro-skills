from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

PUBLIC_SKILLS = (
    "empirical-macro",
    "macro-data",
    "research-design",
    "research-synthesis",
    "robustness-audit",
    "time-series-dynamics",
)
EXCLUDED_PARTS = {
    ".artifacts",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "agent-runs",
    "open_source",
    "sanitized-live",
}
EXCLUDED_NAMES = {
    ".coverage",
    ".DS_Store",
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "INSTALL.md",
    "credentials.json",
    "service-account.json",
}
CREDENTIAL_SUFFIXES = {
    ".key",
    ".p12",
    ".pem",
    ".pfx",
}
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".csv",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
PRIVATE_PREFIXES = (
    "/" + "Users/",
    "/" + "home/",
    "/" + "private/var/",
)
PRIVATE_WORKSPACE_TERMS = (
    "byte" + "dance",
    "学科数据" + "skill",
    "秋" + "招",
    "简历与" + "面试",
    "老师" + "咨询",
    "逐字" + "稿",
)
EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
SECRET_PATTERN = re.compile(
    r"ark-" + r"[A-Za-z0-9-]{12,}|"
    r"Bearer[ \t]+[A-Za-z0-9._-]{8,}|"
    r"Authorization:[ \t]*[A-Za-z0-9._-]{8,}|"
    r"X-Agent-Plan-Key[ \t]*[:=][ \t]*[A-Za-z0-9._-]{8,}|"
    r"(?:aws_secret_access_key|secret_access_key|client_secret|private_key)"
    r'["\']?[ \t]*[:=][ \t]*["\']?[A-Za-z0-9/+_.-]{12,}',
    re.IGNORECASE,
)
TRACE_PATTERN = re.compile(
    r'"trace_' + r'id"\s*:\s*"[A-Za-z0-9._-]{8,}"',
    re.IGNORECASE,
)


def _excluded(relative: Path) -> bool:
    name = relative.name
    return (
        bool(EXCLUDED_PARTS.intersection(relative.parts))
        or name in EXCLUDED_NAMES
        or relative.suffix in {".pyc", ".pyo"}
        or relative.suffix.lower() in CREDENTIAL_SUFFIXES
        or name.startswith(".env.")
        or name.endswith(".env")
    )


def _copy_skill(source: Path, destination: Path) -> int:
    copied = 0
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if _excluded(relative) or path.is_symlink() or not path.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def _reject_tree_symlinks(source: Path) -> None:
    if source.is_symlink() or any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("validation artifacts contain symlink")


def _copy_public_validation_artifacts(
    empirical_source: Path,
    skills_root: Path,
) -> None:
    stages = empirical_source / "fixtures" / "workflow" / "dynamic-gold" / "stages"
    copies = (
        (
            stages / "design_ready",
            skills_root
            / "research-design"
            / "fixtures"
            / "public"
            / "jel-example5-design",
        ),
        (
            stages / "data_ready",
            skills_root
            / "time-series-dynamics"
            / "fixtures"
            / "public"
            / "jel-example5-input-evidence",
        ),
    )
    for source, destination in copies:
        _reject_tree_symlinks(source)
        shutil.copytree(source, destination)


def _directory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _publish(staging: Path, output_dir: Path) -> None:
    backup = output_dir.with_name(f".{output_dir.name}.backup-{uuid4().hex}")
    try:
        if output_dir.exists():
            os.replace(output_dir, backup)
        os.replace(staging, output_dir)
    except BaseException:
        if backup.exists() and not output_dir.exists():
            os.replace(backup, output_dir)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def _publish_if_absent(staging: Path, output_dir: Path) -> bool:
    try:
        os.rename(staging, output_dir)
        return True
    except OSError as error:
        if error.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
            raise
        return False
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _paths_overlap(first: Path, second: Path) -> bool:
    left = first.resolve()
    right = second.resolve()
    return left == right or left in right.parents or right in left.parents


def _validate_output_location(module_root: Path, output_dir: Path) -> None:
    if output_dir.is_symlink() or (output_dir.exists() and not output_dir.is_dir()):
        raise ValueError("snapshot output must be a directory")
    if _paths_overlap(module_root, output_dir):
        raise ValueError("snapshot output overlaps source")


def build_public_snapshot(
    *,
    project_root: Path,
    output_dir: Path,
) -> dict[str, object]:
    module_root = (
        project_root / "30_宏观经济实证Skill" / "02_模块开发"
    )
    _validate_output_location(module_root, output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.staging-",
            dir=output_dir.parent,
        )
    )
    copied = 0
    try:
        empirical = module_root / "empirical-macro"
        open_source = empirical / "open_source"
        _reject_tree_symlinks(open_source)
        shutil.copytree(open_source, staging, dirs_exist_ok=True)
        shutil.copy2(
            empirical / "THIRD_PARTY_NOTICES.md",
            staging / "THIRD_PARTY_NOTICES.md",
        )
        shutil.copy2(empirical / "INSTALL.md", staging / "INSTALL.md")
        license_path = project_root / "LICENSE"
        if license_path.is_file():
            shutil.copy2(license_path, staging / "LICENSE")
        skills_root = staging / "skills"
        for skill in PUBLIC_SKILLS:
            copied += _copy_skill(module_root / skill, skills_root / skill)
        _copy_public_validation_artifacts(empirical, skills_root)
        report = validate_public_snapshot(staging)
        snapshot_checksum = _directory_sha256(staging)
        issue_codes = report["issue_codes"]
        license_pending = issue_codes == ["project_license_missing"]
        if report["valid"]:
            _publish(staging, output_dir)
            published = True
        elif license_pending:
            published = _publish_if_absent(staging, output_dir)
        else:
            shutil.rmtree(staging, ignore_errors=True)
            published = False
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    report["copied_files"] = copied
    report["snapshot_checksum"] = snapshot_checksum
    report["published"] = published
    return report


def _scan_file(path: Path) -> list[str]:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    issues: list[str] = []
    if any(prefix in text for prefix in PRIVATE_PREFIXES):
        issues.append("private_path_found")
    if any(term.lower() in text.lower() for term in PRIVATE_WORKSPACE_TERMS):
        issues.append("private_workspace_term_found")
    if EMAIL_PATTERN.search(text):
        issues.append("email_address_found")
    if SECRET_PATTERN.search(text):
        issues.append("secret_value_found")
    if TRACE_PATTERN.search(text):
        issues.append("raw_trace_id_found")
    return issues


def _plugin_issues(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        plugin = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["plugin_manifest_invalid"]
    expected = {
        "name": "empirical-macro-skills",
        "version": "0.1.0-beta",
        "license": "Apache-2.0",
    }
    if not isinstance(plugin, dict) or any(
        plugin.get(key) != value for key, value in expected.items()
    ):
        return ["plugin_manifest_invalid"]
    return []


def _required_issues(output_dir: Path) -> list[str]:
    issues: list[str] = []
    required = {
        "README.md",
        "INSTALL.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "THIRD_PARTY_NOTICES.md",
        "plugin.json",
        "scripts/scan_public_release.py",
    }
    for name in required:
        if not (output_dir / name).is_file():
            issues.append(f"required_file_missing:{name}")
    if not (output_dir / "LICENSE").is_file():
        issues.append("project_license_missing")
    issues.extend(_plugin_issues(output_dir / "plugin.json"))
    skills_root = output_dir / "skills"
    for skill in PUBLIC_SKILLS:
        root = skills_root / skill
        if not (root / "SKILL.md").is_file():
            issues.append(f"public_skill_missing:{skill}")
        if not (root / "scripts" / "quick_validate.py").is_file():
            issues.append(f"quick_validator_missing:{skill}")
    return issues


def _scan_snapshot(
    output_dir: Path,
) -> tuple[list[str], list[dict[str, str]]]:
    issues: list[str] = []
    findings: list[dict[str, str]] = []
    for path in output_dir.rglob("*"):
        relative = path.relative_to(output_dir)
        if path.is_symlink():
            issues.append("symlink_found")
            findings.append({"path": relative.as_posix(), "issue": "symlink_found"})
        if path.is_file():
            for issue in _scan_file(path):
                issues.append(issue)
                findings.append({"path": relative.as_posix(), "issue": issue})
    return issues, findings


def validate_public_snapshot(output_dir: Path) -> dict[str, object]:
    issues = _required_issues(output_dir)
    scan_issues, findings = _scan_snapshot(output_dir)
    issues.extend(scan_issues)
    skills_root = output_dir / "skills"
    return {
        "valid": not issues,
        "issue_codes": sorted(set(issues)),
        "findings": findings,
        "skill_count": sum(
            (skills_root / skill / "SKILL.md").is_file()
            for skill in PUBLIC_SKILLS
        ),
        "license_status": (
            "present" if (output_dir / "LICENSE").is_file() else "missing"
        ),
    }
