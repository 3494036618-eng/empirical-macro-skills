"""Canonical hashing and content-addressed identifiers."""

from __future__ import annotations

import hashlib
import json


def _canonical_bytes(document: object) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(document: object) -> str:
    return hashlib.sha256(_canonical_bytes(document)).hexdigest()


def content_id(prefix: str, document: object) -> str:
    return f"{prefix}-{canonical_sha256(document)[:32]}"


def estimand_fingerprint(
    request: dict[str, object],
    fields: tuple[str, ...],
) -> str:
    payload = {field: request.get(field) for field in fields}
    return f"sha256:{canonical_sha256(payload)}"
