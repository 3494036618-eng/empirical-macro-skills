"""编译可定位到结构化 Artifact 的 evidence index。"""

from __future__ import annotations

from typing import cast

from research_synthesis.identifiers import content_id
from research_synthesis.models import EnvelopeMap, EvidenceEnvelope


def _artifact_sha(envelope: EvidenceEnvelope, filename: str) -> str:
    for artifact in envelope.artifacts:
        if artifact.get("path") == filename:
            return str(artifact["sha256"])
    raise ValueError(f"artifact_not_indexed:{filename}")


def _record(
    evidence_class: str,
    semantic_role: str,
    artifact_path: str,
    artifact_sha256: str,
    locator_type: str,
    locator_value: str,
) -> dict[str, object]:
    payload = {
        "evidence_class": evidence_class,
        "semantic_role": semantic_role,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
        "locator": {
            "type": locator_type,
            "value": locator_value,
        },
        "status": "verified",
    }
    return {
        "evidence_id": content_id("rs-evidence", payload),
        **payload,
    }


def _design_records(envelope: EvidenceEnvelope) -> list[dict[str, object]]:
    request_sha = _artifact_sha(envelope, "research_request.json")
    plan_sha = _artifact_sha(envelope, "research_plan.json")
    has_audit = any(
        item.get("path") == "identification_audit.json"
        for item in envelope.artifacts
    )
    identification_path = (
        "identification_audit.json" if has_audit else "research_plan.json"
    )
    identification_sha = _artifact_sha(envelope, identification_path)
    identification_locator = (
        "/identification_status" if has_audit else "/claim_eligibility"
    )
    return [
        _record(
            "project_evidence",
            "research_question",
            "reproduction/data-and-evidence/research-design/research_request.json",
            request_sha,
            "json_pointer",
            "/research_question",
        ),
        _record(
            "project_evidence",
            "estimand",
            "reproduction/data-and-evidence/research-design/research_plan.json",
            plan_sha,
            "json_pointer",
            "/estimand",
        ),
        _record(
            "project_evidence",
            "identification",
            (
                "reproduction/data-and-evidence/research-design/"
                f"{identification_path}"
            ),
            identification_sha,
            "json_pointer",
            identification_locator,
        ),
    ]


def _data_records(envelope: EvidenceEnvelope) -> list[dict[str, object]]:
    source_sha = _artifact_sha(envelope, "source-manifest.json")
    return [
        _record(
            "project_evidence",
            "data_identity",
            "reproduction/data-and-evidence/macro-data/source-manifest.json",
            source_sha,
            "json_pointer",
            "/source_commit",
        ),
        _record(
            "project_evidence",
            "license",
            "reproduction/data-and-evidence/macro-data/source-manifest.json",
            source_sha,
            "json_pointer",
            "/license",
        ),
    ]


def _estimate_records(envelope: EvidenceEnvelope) -> list[dict[str, object]]:
    result_sha = _artifact_sha(envelope, "result.json")
    rows = cast(list[dict[str, object]], envelope.statuses["horizon_results"])
    records: list[dict[str, object]] = []
    for index, _ in enumerate(rows):
        base = "reproduction/data-and-evidence/estimator/result.json"
        records.append(
            _record(
                "project_evidence",
                "estimate",
                base,
                result_sha,
                "json_pointer",
                f"/horizon_results/{index}/estimate",
            )
        )
        for field in (
            "standard_error",
            "confidence_lower",
            "confidence_upper",
        ):
            records.append(
                _record(
                    "project_evidence",
                    "uncertainty",
                    base,
                    result_sha,
                    "json_pointer",
                    f"/horizon_results/{index}/{field}",
                ),
            )
    return records


def _robustness_records(
    envelope: EvidenceEnvelope,
) -> list[dict[str, object]]:
    result_sha = _artifact_sha(envelope, "audit-result.json")
    checks_sha = _artifact_sha(envelope, "check-results.json")
    checks = cast(list[dict[str, object]], envelope.statuses["check_results"])
    records = [
        _record(
            "project_evidence",
            "assessment",
            (
                "reproduction/data-and-evidence/robustness-audit/"
                "audit-result.json"
            ),
            result_sha,
            "json_pointer",
            "/assessment",
        )
    ]
    for index, _ in enumerate(checks):
        records.append(
            _record(
                "project_evidence",
                "robustness_check",
                (
                    "reproduction/data-and-evidence/robustness-audit/"
                    "check-results.json"
                ),
                checks_sha,
                "json_pointer",
                f"/{index}",
            )
        )
    return records


def compile_evidence_index(envelopes: EnvelopeMap) -> dict[str, object]:
    """编译只允许结构化 locator 的 evidence index。"""
    records = [
        *_design_records(envelopes["research_design"]),
        *_data_records(envelopes["macro_data"]),
        *_estimate_records(envelopes["estimator"]),
        *_robustness_records(envelopes["robustness_audit"]),
    ]
    payload = {
        "schema_version": "0.1.0",
        "evidence": records,
    }
    return {
        **payload,
        "evidence_index_id": content_id("rs-evidence-index", payload),
    }
