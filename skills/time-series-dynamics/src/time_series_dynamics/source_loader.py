"""Load and verify the pinned Jordà-Taylor Example 5 source."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pandas as pd

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
REQUIRED_MANIFEST_FIELDS = {
    "schema_version",
    "source_title",
    "source_commit",
    "source_url",
    "archive_sha256",
    "license",
    "archive_member",
    "member_sha256",
    "stata_log_member",
    "stata_log_sha256",
    "stata_program_member",
    "stata_program_sha256",
    "sample_start",
    "sample_end",
    "horizons",
}
PINNED_IDENTITY = {
    "source_commit": "655696c1c576b7537c5a939d2c261f0a111ae663",
    "source_url": (
        "https://raw.githubusercontent.com/ojorda/JEL-Code/"
        "655696c1c576b7537c5a939d2c261f0a111ae663/LP_JEL_Replication.zip"
    ),
    "archive_member": (
        "LP_JEL_Replication/Example5_SignificanceBands/aggregatedata_final.dta"
    ),
    "stata_log_member": "LP_JEL_Replication/Example5_SignificanceBands/all.log",
    "stata_program_member": (
        "LP_JEL_Replication/Example5_SignificanceBands/sbands_RR.do"
    ),
    "sample_start": "1985Q1",
    "sample_end": "2007Q4",
    "horizons": list(range(18)),
}


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def load_source_manifest(path: Path) -> dict[str, object]:
    document = cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )
    missing = sorted(REQUIRED_MANIFEST_FIELDS - document.keys())
    if missing:
        raise ValueError(f"source manifest missing fields: {', '.join(missing)}")
    if document["schema_version"] != "0.1.0":
        raise ValueError("unsupported source manifest version")
    if document["license"] != "CC0-1.0":
        raise ValueError("unsupported source license")
    if not str(document["source_url"]).startswith("https://"):
        raise ValueError("source URL must use HTTPS")
    if any(document[field] != value for field, value in PINNED_IDENTITY.items()):
        raise ValueError("unpinned source manifest identity")
    checksum_fields = (
        "archive_sha256",
        "member_sha256",
        "stata_log_sha256",
        "stata_program_sha256",
    )
    if any(not _is_sha256(document[field]) for field in checksum_fields):
        raise ValueError("source manifest contains invalid checksum")
    return document


def verify_file_checksum(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError(f"checksum mismatch for {path.name}: {actual}")


def _period_index(frame: pd.DataFrame) -> pd.PeriodIndex:
    dates = pd.to_datetime(frame["qdate"], errors="raise")
    return pd.PeriodIndex(dates, freq="Q")


def _validate_quarterly_axis(frame: pd.DataFrame, start: str, end: str) -> None:
    periods = _period_index(frame)
    if periods.duplicated().any():
        raise ValueError("duplicate quarterly observations")
    expected = pd.period_range(start=start, end=end, freq="Q")
    if not periods.equals(expected):
        raise ValueError("quarterly coverage is incomplete or out of order")


def load_jel_example5(
    path: Path,
    *,
    start: str = "1985Q1",
    end: str = "2007Q4",
) -> pd.DataFrame:
    frame = pd.read_stata(path, convert_dates=True)
    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing_columns:
        raise ValueError(f"missing required columns: {', '.join(missing_columns)}")
    selected = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    periods = _period_index(selected)
    mask = (periods >= pd.Period(start, freq="Q")) & (
        periods <= pd.Period(end, freq="Q")
    )
    selected = selected.loc[mask].sort_values("qdate").reset_index(drop=True)
    if selected.empty:
        raise ValueError("requested sample is empty")
    missing_counts = selected.isna().sum()
    columns_with_missing = sorted(
        str(column) for column, count in missing_counts.items() if count
    )
    if columns_with_missing:
        raise ValueError(
            f"missing values in requested sample: {', '.join(columns_with_missing)}"
        )
    _validate_quarterly_axis(selected, start, end)
    return selected
