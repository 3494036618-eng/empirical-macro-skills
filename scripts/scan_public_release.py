#!/usr/bin/env python3
"""Reject private, generated, or credential-bearing public release files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ALLOWED_TOP_LEVEL = {
    ".github",
    ".gitignore",
    ".npmignore",
    "CONTRIBUTING.md",
    "INSTALL.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "bin",
    "docs",
    "package.json",
    "plugin.json",
    "scripts",
    "skills",
    "tests",
}
FORBIDDEN_PARTS = {
    ".cache",
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".trae",
    ".venv",
    ".vscode",
    "__pycache__",
    "agent-runs",
    "evidence",
    "platform-hotfix",
    "sanitized-live",
}
FORBIDDEN_NAMES = {
    ".coverage",
    ".DS_Store",
    ".env",
    ".netrc",
    "HOST_ADAPTER_ARCHITECTURE.md",
    "OPEN_SOURCE_RELEASE_IMPLEMENTATION_PLAN.md",
    "PUBLICATION_CHECKLIST.md",
    "openai4s_local_adapter.py",
    "credentials.json",
    "service-account.json",
}
PRIVATE_PATH = re.compile(
    r"/" + r"(?:Users|home|private/var)/",
    re.IGNORECASE,
)
SECRET_VALUE = re.compile(
    r"ark-" + r"[A-Za-z0-9-]{12,}|"
    r"Bearer" + r"[ \t]+[A-Za-z0-9._-]{8,}|"
    r"Authorization" + r":[ \t]*[A-Za-z0-9._-]{8,}|"
    r"X-Agent-Plan-Key" + r"[ \t]*[:=][ \t]*[A-Za-z0-9._-]{8,}|"
    r"(?:api[_-]?key|client_secret|private_key)"
    r'["\']?[ \t]*[:=][ \t]*["\']?[A-Za-z0-9/+_.-]{12,}',
    re.IGNORECASE,
)
RAW_TRACE = re.compile(
    r'"trace_' + r'id"[ \t]*:[ \t]*"[A-Za-z0-9._-]{8,}"',
    re.IGNORECASE,
)
EMAIL = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
PRIVATE_WORKSPACE_TERMS = (
    "byte" + "dance",
    "学科数据" + "skill",
    "秋" + "招",
    "简历与" + "面试",
    "老师" + "咨询",
    "逐字" + "稿",
)
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".csv",
    ".json",
    ".jsonl",
    ".md",
    ".mjs",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def _text_finding_codes(text: str) -> list[str]:
    checks = (
        ("private_path_found", PRIVATE_PATH.search(text)),
        ("secret_value_found", SECRET_VALUE.search(text)),
        ("raw_trace_id_found", RAW_TRACE.search(text)),
        ("email_address_found", EMAIL.search(text)),
        (
            "private_workspace_term_found",
            any(term.lower() in text.lower() for term in PRIVATE_WORKSPACE_TERMS),
        ),
    )
    return [code for code, matched in checks if matched]


def _tracked_paths(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return set()
    return {
        item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item
    }


def _tracked_or_contains(relative: Path, tracked: set[str]) -> bool:
    value = relative.as_posix().rstrip("/")
    prefix = value + "/"
    return value in tracked or any(path.startswith(prefix) for path in tracked)


def scan(
    root: Path,
    *,
    allow_git_metadata: bool = False,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    tracked = _tracked_paths(root) if allow_git_metadata else set()
    observed_top = {path.name for path in root.iterdir()}
    if allow_git_metadata:
        observed_top.discard(".git")
        observed_top.difference_update(
            name
            for name in FORBIDDEN_PARTS
            if not any(
                path == name or path.startswith(name + "/")
                for path in tracked
            )
        )
    for name in sorted(observed_top - ALLOWED_TOP_LEVEL):
        findings.append({"path": name, "code": "unexpected_top_level_entry"})
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        if allow_git_metadata and relative.parts[0] == ".git":
            continue
        if path.is_symlink():
            findings.append({"path": relative_text, "code": "symlink_found"})
            continue
        if FORBIDDEN_PARTS.intersection(relative.parts):
            if allow_git_metadata and not _tracked_or_contains(relative, tracked):
                continue
            findings.append({"path": relative_text, "code": "generated_path_found"})
            continue
        if path.name in FORBIDDEN_NAMES or path.name.startswith(".env."):
            findings.append({"path": relative_text, "code": "credential_file_found"})
            continue
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        findings.extend(
            {"path": relative_text, "code": code}
            for code in _text_finding_codes(text)
        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--allow-git-metadata", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    findings = scan(
        root,
        allow_git_metadata=args.allow_git_metadata,
    )
    report = {
        "schema_version": "0.1.0",
        "root": ".",
        "valid": not findings,
        "finding_count": len(findings),
        "findings": findings,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
