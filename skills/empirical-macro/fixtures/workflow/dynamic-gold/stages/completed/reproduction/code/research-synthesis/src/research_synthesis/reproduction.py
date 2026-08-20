"""组装中文复现说明、代码快照和上游证据。"""

from __future__ import annotations

import json
import platform
import shutil
from pathlib import Path

from research_synthesis.identifiers import runtime_sanitized_json_bytes

CODE_ENTRIES = (
    "src",
    "scripts",
    "schemas",
    "pyproject.toml",
    "uv.lock",
    "SKILL.md",
    "THIRD_PARTY_NOTICES.md",
)
IGNORED = shutil.ignore_patterns(
    ".venv",
    ".cache",
    ".artifacts",
    "__pycache__",
    ".pytest_cache",
    ".coverage",
)


def _assert_no_symlinks(source: Path) -> None:
    candidates = [source]
    if source.is_dir():
        candidates.extend(source.rglob("*"))
    for path in candidates:
        if path.is_symlink():
            raise ValueError(
                f"source_symlink_forbidden:{path.relative_to(source.parent)}"
            )


def _copy_entry(source: Path, target: Path) -> None:
    _assert_no_symlinks(source)
    if source.is_dir():
        shutil.copytree(source, target, ignore=IGNORED)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _copy_code(
    code_root: Path,
    source_roots: dict[str, Path],
) -> int:
    copied = 0
    for name, source_root in sorted(source_roots.items()):
        target_root = code_root / name
        for relative in CODE_ENTRIES:
            source = source_root / relative
            if source.exists():
                _copy_entry(source, target_root / relative)
                copied += 1
    return copied


def _copy_bundles(
    evidence_root: Path,
    bundle_paths: dict[str, Path],
) -> None:
    for role, source in sorted(bundle_paths.items()):
        _assert_no_symlinks(source)
        directory = role.replace("_", "-")
        target = evidence_root / directory
        shutil.copytree(source, target, ignore=IGNORED)
        if role == "robustness_audit":
            checks = json.loads(
                (source / "check-results.json").read_text(encoding="utf-8")
            )
            (target / "check-results.json").write_bytes(
                runtime_sanitized_json_bytes(checks)
            )


def _write_guidance(
    root: Path,
    bundle_count: int,
    data_facts: dict[str, object],
) -> None:
    (root / "README.md").write_text(
        "# 复现说明\n\n"
        "本目录包含生成研究报告所需的代码快照、上游证据、环境和许可证。\n\n"
        f"- 上游证据 bundles：{bundle_count}\n"
        "- 执行顺序和 expected outputs 见 `.audit/reproduction-manifest.json`。\n",
        encoding="utf-8",
    )
    (root / "data-availability-statement.md").write_text(
        "# 数据可用性说明\n\n"
        f"数据：{data_facts['source_title']}。\n\n"
        f"固定版本：`{data_facts['source_commit']}`；"
        f"许可：`{data_facts['license']}`。"
        "公开发布仍受项目 M2 数据发布门禁约束。\n",
        encoding="utf-8",
    )


def _data_facts(bundle_paths: dict[str, Path]) -> dict[str, object]:
    source_path = bundle_paths["macro_data"] / "source-manifest.json"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("source_manifest_invalid")
    return document


def build_reproduction_package(
    staging: Path,
    source_roots: dict[str, Path],
    bundle_paths: dict[str, Path],
) -> dict[str, object]:
    """组装 researcher-facing reproduction 目录。"""
    root = staging / "reproduction"
    code_root = root / "code"
    evidence_root = root / "data-and-evidence"
    environment_root = root / "environment"
    license_root = root / "licenses"
    for path in (code_root, evidence_root, environment_root, license_root):
        path.mkdir(parents=True, exist_ok=True)
    code_entry_count = _copy_code(code_root, source_roots)
    _copy_bundles(evidence_root, bundle_paths)
    environment = {"python": platform.python_version()}
    (environment_root / "runtime.json").write_text(
        json.dumps(environment, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    for name, source_root in sorted(source_roots.items()):
        notice = source_root / "THIRD_PARTY_NOTICES.md"
        if notice.is_file():
            shutil.copyfile(notice, license_root / f"{name}.md")
    _write_guidance(root, len(bundle_paths), _data_facts(bundle_paths))
    return {
        "bundle_count": len(bundle_paths),
        "code_entry_count": code_entry_count,
        "runtime": environment,
    }
