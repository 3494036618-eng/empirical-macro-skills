"""Compatibility facade for macro-data bundle export and validation."""

from pathlib import Path
from typing import Any

from macro_data.bundle_export import _sanitized, export_bundle
from macro_data.bundle_validation import (
    _contains_secret,
)
from macro_data.bundle_validation import (
    validate_bundle as validate_legacy_bundle,
)
from macro_data.completion_export import export_completion_bundle
from macro_data.completion_validation import validate_completion_bundle


def validate_bundle(output_dir: Path) -> dict[str, Any]:
    if (output_dir / "completion_manifest.json").is_file():
        return validate_completion_bundle(output_dir)
    return validate_legacy_bundle(output_dir)

__all__ = [
    "_contains_secret",
    "_sanitized",
    "export_bundle",
    "export_completion_bundle",
    "validate_bundle",
]
