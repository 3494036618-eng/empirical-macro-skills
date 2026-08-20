"""重算 research package 的内部语义。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from research_synthesis.identifiers import content_id, sha256_file


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _evidence_checksum_errors(
    output_dir: Path,
    evidence: list[dict[str, object]],
) -> list[str]:
    expected = {
        str(item["artifact_path"]): str(item["artifact_sha256"]).removeprefix(
            "sha256:"
        )
        for item in evidence
    }
    errors = []
    for relative, digest in sorted(expected.items()):
        path = output_dir / relative
        if not path.is_file() or sha256_file(path) != digest:
            errors.append(f"evidence_artifact_checksum_mismatch:{relative}")
    return errors


def _reproduction_output_errors(output_dir: Path) -> list[str]:
    document = cast(
        dict[str, object],
        _load(output_dir / ".audit" / "reproduction-manifest.json"),
    )
    expected = cast(dict[str, str], document["expected_outputs"])
    errors = []
    for relative, digest in sorted(expected.items()):
        path = output_dir / relative
        observed = f"sha256:{sha256_file(path)}" if path.is_file() else None
        if observed != digest:
            errors.append(
                f"reproduction_output_checksum_mismatch:{relative}"
            )
    return errors


def _claim_identity_errors(claims: list[dict[str, object]]) -> list[str]:
    for claim in claims:
        payload = {key: value for key, value in claim.items() if key != "claim_id"}
        if claim["claim_id"] != content_id("rs-claim", payload):
            return ["claim_id_mismatch"]
    return []


def _content_identity_errors(
    evidence_doc: dict[str, object],
    claims_doc: dict[str, object],
    limits_doc: dict[str, object],
    result_doc: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    evidence = cast(list[dict[str, object]], evidence_doc["evidence"])
    evidence_item_mismatch = any(
        item["evidence_id"]
        != content_id(
            "rs-evidence",
            {key: value for key, value in item.items() if key != "evidence_id"},
        )
        for item in evidence
    )
    if evidence_item_mismatch:
        errors.append("evidence_id_mismatch")
    evidence_payload = {
        "schema_version": evidence_doc["schema_version"],
        "evidence": evidence,
    }
    if not evidence_item_mismatch and evidence_doc[
        "evidence_index_id"
    ] != content_id(
        "rs-evidence-index",
        evidence_payload,
    ):
        errors.append("evidence_index_id_mismatch")
    claims = cast(list[dict[str, object]], claims_doc["claims"])
    claim_errors = _claim_identity_errors(claims)
    errors.extend(claim_errors)
    claim_payload = {
        "schema_version": claims_doc["schema_version"],
        "effective_claim_eligibility": claims_doc[
            "effective_claim_eligibility"
        ],
        "claims": claims,
    }
    if not claim_errors and claims_doc["claim_ledger_id"] != content_id(
        "rs-claim-ledger",
        claim_payload,
    ):
        errors.append("claim_ledger_id_mismatch")
    errors.extend(_limitation_identity_errors(limits_doc))
    expected_result = content_id(
        "rs-result",
        {
            "request_ref": result_doc["request_ref"],
            "claim_ledger_id": claims_doc["claim_ledger_id"],
            "evidence_index_id": evidence_doc["evidence_index_id"],
            "limitations_id": limits_doc["limitations_id"],
        },
    )
    if result_doc["result_id"] != expected_result:
        errors.append("result_id_mismatch")
    return errors


def _limitation_identity_errors(
    limits_doc: dict[str, object],
) -> list[str]:
    limitations = cast(list[dict[str, object]], limits_doc["limitations"])
    errors = []
    item_mismatch = any(
        item["limitation_id"]
        != content_id(
            "rs-limitation",
            {
                key: value
                for key, value in item.items()
                if key != "limitation_id"
            },
        )
        for item in limitations
    )
    if item_mismatch:
        errors.append("limitation_id_mismatch")
    payload = {
        "schema_version": limits_doc["schema_version"],
        "limitations": limitations,
    }
    if not item_mismatch and limits_doc["limitations_id"] != content_id(
        "rs-limitations",
        payload,
    ):
        errors.append("limitations_id_mismatch")
    return errors


def _limitation_report_errors(
    report: str,
    limitations: list[dict[str, object]],
) -> list[str]:
    marker = "## 6. 结论与限制"
    if marker not in report:
        return ["report_limitation_set_mismatch"]
    section = report.split(marker, 1)[1]
    report_statements = {
        line.removeprefix("- ")
        for line in section.splitlines()
        if line.startswith("- ")
    }
    ledger_statements = {str(item["statement"]) for item in limitations}
    if report_statements != ledger_statements:
        return ["report_limitation_set_mismatch"]
    return []


def _source_bundle_errors(output_dir: Path) -> list[str]:
    root = output_dir / "reproduction" / "data-and-evidence" / "macro-data"
    document = cast(
        dict[str, object],
        _load(root / "input-evidence-manifest.json"),
    )
    expected = cast(dict[str, str], document["file_checksums"])
    errors = []
    for filename, digest in sorted(expected.items()):
        path = root / filename
        if not path.is_file() or sha256_file(path) != digest:
            errors.append(
                f"source_bundle_checksum_mismatch:macro-data/{filename}"
            )
    return errors


def _required_limitation_errors(
    output_dir: Path,
    limitations: list[dict[str, object]],
) -> list[str]:
    evidence_root = output_dir / "reproduction" / "data-and-evidence"
    expected: set[str] = set()
    audit_path = evidence_root / "research-design" / "identification_audit.json"
    try:
        if audit_path.is_file():
            audit = cast(dict[str, object], _load(audit_path))
            assumptions = cast(list[dict[str, object]], audit["assumptions"])
            threats = cast(list[dict[str, object]], audit["threats"])
            expected.update(
                str(item["code"])
                for item in assumptions
                if item.get("status") == "unresolved"
            )
            expected.update(
                str(item["code"])
                for item in threats
                if item.get("status") == "open"
            )
        robustness = cast(
            dict[str, object],
            _load(evidence_root / "robustness-audit" / "audit-result.json"),
        )
        estimator = cast(
            dict[str, object],
            _load(evidence_root / "estimator" / "result.json"),
        )
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return ["limitation_sources_unreadable"]
    if robustness.get("plan_timing") == "post_result_exploratory":
        expected.add("post_result_exploratory")
    if estimator.get("interval_scope") == "pointwise":
        expected.add("pointwise_not_simultaneous")
    observed = {
        str(item["statement"]).split(":", 1)[0]
        for item in limitations
    }
    return [
        f"required_limitation_missing:{code}"
        for code in sorted(expected - observed)
    ]


def semantic_errors(output_dir: Path) -> list[str]:
    """检查 ledger references 和 report 内容一致性。"""
    try:
        evidence_doc = cast(
            dict[str, object],
            _load(output_dir / ".audit" / "evidence-index.json"),
        )
        claims_doc = cast(
            dict[str, object],
            _load(output_dir / ".audit" / "claim-ledger.json"),
        )
        limits_doc = cast(
            dict[str, object],
            _load(output_dir / ".audit" / "limitations.json"),
        )
        result_doc = cast(
            dict[str, object],
            _load(output_dir / ".audit" / "result.json"),
        )
        report = (output_dir / "research-report.md").read_text(
            encoding="utf-8"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return ["semantic_documents_unreadable"]
    evidence = cast(list[dict[str, object]], evidence_doc["evidence"])
    claims = cast(list[dict[str, object]], claims_doc["claims"])
    limitations = cast(
        list[dict[str, object]],
        limits_doc["limitations"],
    )
    evidence_ids = {str(item["evidence_id"]) for item in evidence}
    claim_ids = {str(item["claim_id"]) for item in claims}
    errors: list[str] = []
    if len(evidence_ids) != len(evidence):
        errors.append("duplicate_evidence_id")
    if len(claim_ids) != len(claims):
        errors.append("duplicate_claim_id")
    if any(
        not set(cast(list[str], claim["evidence_refs"])) <= evidence_ids
        for claim in claims
    ):
        errors.append("claim_evidence_reference_mismatch")
    if any(
        not set(cast(list[str], item["source_refs"])) <= evidence_ids
        or not set(cast(list[str], item["affected_claim_refs"])) <= claim_ids
        for item in limitations
    ):
        errors.append("limitation_reference_mismatch")
    if any(str(claim["report_text"]) not in report for claim in claims):
        errors.append("report_claim_mismatch")
    if any(str(item["statement"]) not in report for item in limitations):
        errors.append("report_limitation_mismatch")
    errors.extend(_evidence_checksum_errors(output_dir, evidence))
    errors.extend(_reproduction_output_errors(output_dir))
    identity_errors = (
        _content_identity_errors(
            evidence_doc,
            claims_doc,
            limits_doc,
            result_doc,
        )
    )
    if identity_errors:
        return identity_errors
    errors.extend(_limitation_report_errors(report, limitations))
    errors.extend(_source_bundle_errors(output_dir))
    errors.extend(_required_limitation_errors(output_dir, limitations))
    return errors
