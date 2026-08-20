"""Fetch the pinned Jordà-Taylor Example 5 replication artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen
from zipfile import ZipFile, ZipInfo

from time_series_dynamics.source_loader import (
    load_source_manifest,
    verify_file_checksum,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    PROJECT_ROOT / "fixtures" / "external" / "jorda-taylor-example5.source.json"
)


def _member_is_unsafe(info: ZipInfo) -> bool:
    path = PurePosixPath(info.filename)
    mode = info.external_attr >> 16
    return path.is_absolute() or ".." in path.parts or stat.S_ISLNK(mode)


def _allowed_members(manifest: dict[str, object]) -> dict[str, tuple[str, str]]:
    fields = {
        "archive_member": ("aggregatedata_final.dta", "member_sha256"),
        "stata_log_member": ("all.log", "stata_log_sha256"),
        "stata_program_member": ("sbands_RR.do", "stata_program_sha256"),
    }
    return {
        str(manifest[source_field]): (filename, str(manifest[checksum_field]))
        for source_field, (filename, checksum_field) in fields.items()
        if source_field in manifest and checksum_field in manifest
    }

def extract_allowlisted(
    archive_path: Path,
    output_dir: Path,
    manifest: dict[str, object],
) -> dict[str, Path]:
    allowed = _allowed_members(manifest)
    with ZipFile(archive_path) as archive:
        infos = archive.infolist()
        unsafe = [info.filename for info in infos if _member_is_unsafe(info)]
        if unsafe:
            raise ValueError(f"unsafe archive member: {unsafe[0]}")
        present = {info.filename for info in infos}
        missing = sorted(set(allowed) - present)
        if missing:
            raise ValueError(f"required archive member missing: {missing[0]}")
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted: dict[str, Path] = {}
        for member, (filename, checksum) in allowed.items():
            target = output_dir / filename
            with archive.open(member) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            verify_file_checksum(target, checksum)
            extracted[filename] = target
    return extracted


def fetch_example5(
    output_dir: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Path]:
    manifest = load_source_manifest(manifest_path)
    source_url = str(manifest["source_url"])
    with tempfile.TemporaryDirectory(prefix="jel-example5-") as temporary:
        archive_path = Path(temporary) / "replication.zip"
        with urlopen(source_url, timeout=120) as response:  # noqa: S310
            with archive_path.open("wb") as destination:
                shutil.copyfileobj(response, destination)
        verify_file_checksum(archive_path, str(manifest["archive_sha256"]))
        return extract_allowlisted(archive_path, output_dir, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    extracted = fetch_example5(args.output, args.manifest)
    print(
        json.dumps(
            {"artifacts": sorted(extracted), "output_dir": str(args.output)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
