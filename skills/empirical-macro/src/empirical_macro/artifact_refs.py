from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath


def resolve_artifact_path(project_root: Path, relative_path: str) -> Path:
    portable = PurePosixPath(relative_path)
    windows = PureWindowsPath(relative_path)
    if (
        not relative_path
        or portable.is_absolute()
        or windows.is_absolute()
        or "\\" in relative_path
        or ".." in portable.parts
    ):
        raise ValueError(f"relative artifact path required: {relative_path}")
    root = project_root.resolve()
    candidate = (root / Path(*portable.parts)).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"relative artifact path escapes root: {relative_path}")
    return candidate


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"artifact file is missing: {path.name}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()
