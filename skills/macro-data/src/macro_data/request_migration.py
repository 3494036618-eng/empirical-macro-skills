"""Lossless request migration into the DataPro-first 0.3 contract."""

from __future__ import annotations

import copy
from typing import Any, cast

from macro_data.contracts import validate_document

_SAFETY_FIELDS: dict[str, object] = {
    "completion_scope": "missing_cells_only",
    "preserve_datapro_observations": True,
    "replace_primary_observations": False,
    "allow_semantic_substitute": False,
    "allow_cross_source_stitching": False,
    "identity_match_policy": "exact_native_or_approved_mapping",
    "overlap_policy": "validate_without_replacement",
}


def migrate_request_v02_to_v03(document: dict[str, Any]) -> dict[str, Any]:
    """Return a validated 0.3 copy without changing the legacy request."""
    validate_document("request", document)
    if document["schema_version"] != "0.2.0-beta":
        raise ValueError("request migration requires schema_version '0.2.0-beta'")

    migrated = copy.deepcopy(document)
    legacy_policy = cast(dict[str, Any], migrated["fallback_policy"])
    legacy_mode = cast(str, legacy_policy["mode"])
    mode = (
        "allow_official_missing_only"
        if legacy_mode == "allow_official"
        else legacy_mode
    )
    migrated["schema_version"] = "0.3.0-beta"
    migrated["preferred_sources"] = _datapro_first(
        cast(list[str], migrated["preferred_sources"])
    )
    migrated["fallback_policy"] = {
        "mode": mode,
        "allowed_sources": copy.deepcopy(legacy_policy["allowed_sources"]),
        **_SAFETY_FIELDS,
    }
    validate_document("request", migrated)
    return migrated


def _datapro_first(sources: list[str]) -> list[str]:
    return ["datapro", *(source for source in sources if source != "datapro")]
