"""research-synthesis 的不可变边界模型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BundleReference:
    bundle_ref_id: str
    artifact_role: str
    skill_name: str
    skill_version: str
    bundle_path: Path
    manifest_path: Path
    expected_manifest_sha256: str
    expected_ids: dict[str, str]
    required: bool


@dataclass(frozen=True)
class ResolvedBundle:
    reference: BundleReference
    absolute_path: Path
    manifest_path: Path
    manifest_sha256: str


@dataclass(frozen=True)
class ValidationEvidence:
    status: str
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    issue_codes: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceEnvelope:
    artifact_role: str
    skill_name: str
    identities: dict[str, str]
    statuses: dict[str, object]
    claim_eligibility: str
    artifacts: tuple[dict[str, object], ...]
    runtime: dict[str, str]
    license_facts: tuple[dict[str, object], ...]
    warnings: tuple[str, ...]


EnvelopeMap = dict[str, EvidenceEnvelope]


@dataclass(frozen=True)
class ReportInputs:
    request: dict[str, object]
    evidence_index: dict[str, object]
    claim_ledger: dict[str, object]
    limitations: dict[str, object]
    envelopes: EnvelopeMap
