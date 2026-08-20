from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from scripts.fetch_jel_example5 import extract_allowlisted
from time_series_dynamics.source_loader import (
    load_jel_example5,
    load_source_manifest,
    verify_file_checksum,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = (
    PROJECT_ROOT / "fixtures" / "external" / "jorda-taylor-example5.source.json"
)
REQUIRED_COLUMNS = (
    "qdate",
    "rr_shock",
    "lcpi",
    "lrgdp",
    "stir",
    "dlcpi",
    "dlrgdp",
    "dstir",
)


def _write_stata_fixture(path: Path, *, drop: str | None = None) -> None:
    frame = pd.DataFrame(
        {
            "qdate": pd.date_range("1985-01-01", periods=8, freq="QS"),
            "rr_shock": [0.1, -0.2, 0.0, 0.3, -0.1, 0.0, 0.2, -0.3],
            "lcpi": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7],
            "lrgdp": [2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7],
            "stir": [8.0, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7],
            "dlcpi": [0.1] * 8,
            "dlrgdp": [0.1] * 8,
            "dstir": [0.1] * 8,
        }
    )
    if drop is not None:
        frame = frame.drop(columns=drop)
    frame.to_stata(path, write_index=False)


def test_frozen_source_manifest_has_verified_identity_and_checksums() -> None:
    manifest = load_source_manifest(SOURCE_MANIFEST)

    assert manifest["source_commit"] == (
        "655696c1c576b7537c5a939d2c261f0a111ae663"
    )
    assert manifest["license"] == "CC0-1.0"
    assert manifest["archive_sha256"] == (
        "8fa0ad974eda885e7fc9570b601ca619f4b6216d6605cd2e8e1c7f2fbac246f6"
    )


def test_checksum_verification_rejects_tampered_file(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"original")
    expected = hashlib.sha256(b"original").hexdigest()

    verify_file_checksum(artifact, expected)
    artifact.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_file_checksum(artifact, expected)


def test_loader_filters_complete_contiguous_quarterly_sample(tmp_path: Path) -> None:
    source = tmp_path / "example.dta"
    _write_stata_fixture(source)

    result = load_jel_example5(source, start="1985Q1", end="1986Q4")

    assert tuple(result.columns) == REQUIRED_COLUMNS
    assert result.shape == (8, 8)
    assert result["qdate"].dt.to_period("Q").astype(str).tolist() == [
        "1985Q1",
        "1985Q2",
        "1985Q3",
        "1985Q4",
        "1986Q1",
        "1986Q2",
        "1986Q3",
        "1986Q4",
    ]


def test_loader_rejects_missing_required_column(tmp_path: Path) -> None:
    source = tmp_path / "missing.dta"
    _write_stata_fixture(source, drop="rr_shock")

    with pytest.raises(ValueError, match="missing required columns: rr_shock"):
        load_jel_example5(source, start="1985Q1", end="1986Q4")


def test_loader_rejects_incomplete_or_empty_quarterly_sample(tmp_path: Path) -> None:
    source = tmp_path / "example.dta"
    _write_stata_fixture(source)
    incomplete = pd.read_stata(source).drop(index=3)
    incomplete.to_stata(source, write_index=False)

    with pytest.raises(ValueError, match="quarterly coverage is incomplete"):
        load_jel_example5(source, start="1985Q1", end="1986Q4")
    with pytest.raises(ValueError, match="requested sample is empty"):
        load_jel_example5(source, start="1990Q1", end="1990Q4")


def test_loader_rejects_manifest_tampering(tmp_path: Path) -> None:
    document = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    document["license"] = "unknown"
    tampered = tmp_path / "source.json"
    tampered.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported source license"):
        load_source_manifest(tampered)

    document.pop("source_commit")
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="source manifest missing fields"):
        load_source_manifest(tampered)

    document = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    document["source_url"] = "https://example.com/unapproved.zip"
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="unpinned source manifest identity"):
        load_source_manifest(tampered)

    document = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    document["archive_member"] = "unapproved/data.dta"
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="unpinned source manifest identity"):
        load_source_manifest(tampered)


def test_fetcher_rejects_unsafe_archive_member(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", "unsafe")

    with pytest.raises(ValueError, match="unsafe archive member"):
        extract_allowlisted(archive, tmp_path / "output", {})

    assert not (tmp_path / "escape.txt").exists()
