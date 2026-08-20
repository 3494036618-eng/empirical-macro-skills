"""Canonical domain identities shared across providers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SeriesIdentity:
    provider: str
    dataset_id: str | None
    series_key: str | None
    entity_code: str | None
    indicator_code: str | None
    frequency: str | None
    identity_id: str

    @classmethod
    def from_native(
        cls,
        *,
        provider: str,
        dataset_id: str | None,
        series_key: str | None,
        entity_code: str | None,
        indicator_code: str | None,
        frequency: str | None,
    ) -> SeriesIdentity:
        native = {
            "provider": provider,
            "dataset_id": dataset_id,
            "series_key": series_key,
            "entity_code": entity_code,
            "indicator_code": indicator_code,
            "frequency": frequency,
        }
        canonical = json.dumps(
            native,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        identity_id = "sha256:" + hashlib.sha256(canonical).hexdigest()
        return cls(
            provider=provider,
            dataset_id=dataset_id,
            series_key=series_key,
            entity_code=entity_code,
            indicator_code=indicator_code,
            frequency=frequency,
            identity_id=identity_id,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
