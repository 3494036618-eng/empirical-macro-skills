from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, cast
from uuid import uuid4

from empirical_macro import runtime_environment as runtime
from empirical_macro.artifact_refs import resolve_artifact_path, sha256_file
from empirical_macro.contracts import validate_document

HostName = Literal["generic", "trae", "codex", "claude-code"]
SUITE_SKILLS = (
    "empirical-macro",
    "macro-data",
    "research-design",
    "research-synthesis",
    "robustness-audit",
    "time-series-dynamics",
)
MANIFEST_NAME = "empirical-macro-install-manifest.json"
SOURCE_EXCLUDED_PARTS = {
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
}


@dataclass(frozen=True, slots=True)
class InstallTarget:
    host: HostName
    root: Path


@dataclass(frozen=True, slots=True)
class SourceFile:
    skill: str
    relative_path: str
    source: Path
    sha256: str


def _source_files(source_root: Path) -> tuple[SourceFile, ...]:
    entries: list[SourceFile] = []
    for skill in SUITE_SKILLS:
        skill_root = source_root / skill
        if skill_root.is_symlink() or not (skill_root / "SKILL.md").is_file():
            raise ValueError(f"invalid or linked source skill: {skill}")
        for source in sorted(
            path
            for path in skill_root.rglob("*")
            if path.is_file()
            and not SOURCE_EXCLUDED_PARTS.intersection(
                path.relative_to(skill_root).parts
            )
        ):
            if source.is_symlink():
                raise ValueError(f"source suite contains symlink: {skill}")
            relative = f"{skill}/{source.relative_to(skill_root).as_posix()}"
            entries.append(SourceFile(skill, relative, source, sha256_file(source)))
    return tuple(entries)


def _load_manifest(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("install manifest must be an object")
    manifest = cast(dict[str, object], document)
    validate_document("install_manifest", manifest)
    _validate_manifest_semantics(manifest)
    return manifest


def _manifest_file_checksum(entries: Iterable[tuple[str, str]]) -> str:
    pairs = sorted(entries)
    payload = "\n".join(f"{path}\t{checksum}" for path, checksum in pairs).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _validate_manifest_semantics(manifest: dict[str, object]) -> None:
    if manifest["target_root"] != ".":
        raise ValueError("install manifest target root mismatch")
    files = cast(list[dict[str, object]], manifest["files"])
    seen: set[str] = set()
    for item in files:
        skill = cast(str, item["skill"])
        relative = cast(str, item["path"])
        parts = PurePosixPath(relative).parts
        if len(parts) < 2 or parts[0] != skill:
            raise ValueError("manifest path does not belong to skill")
        if relative in seen:
            raise ValueError("install manifest contains duplicate path")
        seen.add(relative)
    snapshot_checksum = _manifest_file_checksum(
        (cast(str, item["path"]), cast(str, item["sha256"]))
        for item in files
    )
    if manifest["source_snapshot_checksum"] != snapshot_checksum:
        raise ValueError("install manifest snapshot checksum mismatch")
    expected_id = "install-" + hashlib.sha256(
        f"{manifest['host']}:{snapshot_checksum}".encode()
    ).hexdigest()[:32]
    if manifest["manifest_id"] != expected_id:
        raise ValueError("install manifest identity mismatch")


def _manifest_checksums(manifest: dict[str, object] | None) -> dict[str, str]:
    if manifest is None:
        return {}
    files = cast(list[dict[str, object]], manifest["files"])
    return {cast(str, item["path"]): cast(str, item["sha256"]) for item in files}


def _preflight_target(
    target: InstallTarget,
    sources: tuple[SourceFile, ...],
    managed: dict[str, str],
) -> None:
    if target.host not in {"generic", "trae", "codex", "claude-code"}:
        raise ValueError(f"unsupported install host: {target.host}")
    if target.root.exists():
        for path in target.root.rglob("*"):
            if path.is_symlink() and not runtime.inside_managed_runtime(
                path, target.root, SUITE_SKILLS
            ):
                raise ValueError("target suite contains symlink")
    for entry in sources:
        destination = target.root / entry.relative_path
        if not destination.exists():
            continue
        previous = managed.get(entry.relative_path)
        if previous is None:
            raise ValueError(f"unmanaged target file: {entry.relative_path}")
        if not destination.is_file() or sha256_file(destination) != previous:
            raise ValueError(f"managed target file changed: {entry.relative_path}")


def _snapshot_checksum(sources: tuple[SourceFile, ...]) -> str:
    return _manifest_file_checksum(
        (entry.relative_path, entry.sha256) for entry in sources
    )


def _target_fingerprint(root: Path) -> str:
    if not root.exists():
        return "absent"
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            kind = "symlink"
            payload = os.readlink(path).encode()
        elif path.is_file():
            kind = "file"
            payload = path.read_bytes()
        elif path.is_dir():
            kind = "directory"
            payload = b""
        else:
            kind = "other"
            payload = b""
        digest.update(f"{kind}:{relative}".encode())
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _manifest_document(
    target: InstallTarget,
    sources: tuple[SourceFile, ...],
) -> dict[str, object]:
    snapshot_checksum = _snapshot_checksum(sources)
    manifest_id = "install-" + hashlib.sha256(
        f"{target.host}:{snapshot_checksum}".encode()
    ).hexdigest()[:32]
    return {
        "schema_version": "0.1.0-beta",
        "manifest_id": manifest_id,
        "installed_at": datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "host": target.host,
        "target_root": ".",
        "source_snapshot_checksum": snapshot_checksum,
        "files": [
            {
                "skill": entry.skill,
                "path": entry.relative_path,
                "sha256": entry.sha256,
            }
            for entry in sources
        ],
    }


def _prepare_staging(
    target: InstallTarget,
    sources: tuple[SourceFile, ...],
    managed: dict[str, str],
) -> Path:
    target.root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{target.root.name}.staging-",
            dir=target.root.parent,
        )
    )
    if target.root.exists():
        shutil.copytree(
            target.root,
            staging,
            dirs_exist_ok=True,
            symlinks=True,
        )
    source_paths = {entry.relative_path for entry in sources}
    for relative, checksum in managed.items():
        stale = staging / relative
        if relative not in source_paths and stale.is_file() and sha256_file(stale) == checksum:
            stale.unlink()
    for entry in sources:
        destination = staging / entry.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry.source, destination)
    (staging / MANIFEST_NAME).unlink(missing_ok=True)
    return staging


def _run_quick_validators(staging: Path) -> None:
    runtime.run_quick_validators(staging, SUITE_SKILLS)


def _publish(
    staging: Path,
    target: Path,
    expected_fingerprint: str,
) -> None:
    if _target_fingerprint(target) != expected_fingerprint:
        raise ValueError("target changed during install")
    backup = target.with_name(f".{target.name}.backup-{uuid4().hex}")
    try:
        if target.exists():
            os.replace(target, backup)
        os.replace(staging, target)
    except BaseException:
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def _remove_if_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError as error:
        if error.errno not in {errno.ENOENT, errno.ENOTEMPTY, errno.EEXIST}:
            raise


def _uninstall_candidates(
    target_root: Path,
    files: list[dict[str, object]],
) -> tuple[list[Path], list[str]]:
    removable: list[Path] = []
    retained: list[str] = []
    for item in files:
        relative = cast(str, item["path"])
        path = resolve_artifact_path(target_root, relative)
        if not path.exists():
            continue
        if path.is_file() and sha256_file(path) == item["sha256"]:
            removable.append(path)
        else:
            retained.append(relative)
    return removable, retained


def install_suite(
    *,
    source_root: Path,
    target: InstallTarget,
    dry_run: bool,
) -> dict[str, object]:
    sources = _source_files(source_root)
    manifest_path = target.root / MANIFEST_NAME
    previous_manifest = _load_manifest(manifest_path)
    managed = _manifest_checksums(previous_manifest)
    _preflight_target(target, sources, managed)
    target_fingerprint = _target_fingerprint(target.root)
    report: dict[str, object] = {
        "dry_run": dry_run,
        "host": target.host,
        "installed_skills": list(SUITE_SKILLS),
        "file_count": len(sources),
        "runtime_environments": [
            f"{skill}/.venv"
            for skill in SUITE_SKILLS
            if (source_root / skill / "pyproject.toml").is_file()
        ],
    }
    if dry_run:
        return report
    staging = _prepare_staging(target, sources, managed)
    try:
        _run_quick_validators(staging)
        manifest = _manifest_document(target, sources)
        validate_document("install_manifest", manifest)
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _publish(staging, target.root, target_fingerprint)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    report["manifest"] = MANIFEST_NAME
    return report


def uninstall_suite(
    *,
    target: InstallTarget,
    manifest_path: Path,
    dry_run: bool,
) -> dict[str, object]:
    target_root = target.root.resolve()
    if manifest_path.resolve().parent != target_root:
        raise ValueError("manifest must be inside target root")
    manifest = _load_manifest(manifest_path)
    if manifest is None or manifest.get("host") != target.host:
        raise ValueError("install manifest missing or host mismatch")
    files = cast(list[dict[str, object]], manifest["files"])
    removable, retained = _uninstall_candidates(target_root, files)
    report: dict[str, object] = {
        "dry_run": dry_run,
        "removed_files": [str(path.relative_to(target_root)) for path in removable],
        "retained_modified_files": retained,
        "removed_runtime_environments": runtime.remove_managed_runtimes(
            target_root,
            SUITE_SKILLS,
            dry_run=True,
        ),
    }
    if dry_run:
        return report
    runtime.remove_managed_runtimes(target_root, SUITE_SKILLS, dry_run=False)
    checksums = {
        cast(str, item["path"]): cast(str, item["sha256"])
        for item in files
    }
    removed: list[str] = []
    for path in removable:
        relative = path.relative_to(target_root).as_posix()
        if (
            path.is_symlink()
            or not path.is_file()
            or sha256_file(path) != checksums[relative]
        ):
            retained.append(relative)
            continue
        path.unlink()
        removed.append(relative)
    for skill in SUITE_SKILLS:
        skill_root = target_root / skill
        for directory in sorted(
            (path for path in skill_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            _remove_if_empty(directory)
        if skill_root.is_dir():
            _remove_if_empty(skill_root)
    manifest_path.unlink()
    report["removed_files"] = removed
    report["retained_modified_files"] = sorted(set(retained))
    return report
