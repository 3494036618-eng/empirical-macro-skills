"""Map immutable upstream threats to executed audit evidence."""

from __future__ import annotations

from typing import cast


def _audit_status(results: list[dict[str, object]]) -> str:
    if not results:
        return "unexamined"
    statuses = {str(item["status"]) for item in results}
    if statuses & {"sensitive", "failed"}:
        return "sensitivity_detected"
    if statuses & {"error", "blocked", "inconclusive"}:
        return "partially_examined"
    if statuses == {"not_applicable"}:
        return "unexamined"
    if statuses <= {"passed", "not_applicable"}:
        return "no_sensitivity_detected"
    return "partially_examined"


def build_threat_ledger(
    handoff: dict[str, object],
    check_results: list[dict[str, object]],
) -> list[dict[str, object]]:
    threats = cast(list[dict[str, object]], handoff.get("threats", []))
    ledger: list[dict[str, object]] = []
    for threat in threats:
        code = str(threat["code"])
        mapped = [
            item
            for item in check_results
            if code
            in {
                str(reference)
                for reference in cast(list[object], item.get("threat_refs", []))
            }
        ]
        ledger.append(
            {
                "threat_code": code,
                "upstream_severity": threat["severity"],
                "upstream_status": threat["status"],
                "mapped_check_ids": sorted(
                    {str(item["check_id"]) for item in mapped}
                ),
                "executed_check_ids": sorted(
                    {
                        str(item["check_id"])
                        for item in mapped
                        if item.get("status") != "not_applicable"
                    }
                ),
                "audit_status": _audit_status(mapped),
                "evidence_refs": sorted(
                    {
                        str(reference)
                        for item in mapped
                        for reference in cast(
                            list[object],
                            item.get("evidence_refs", []),
                        )
                    }
                ),
                "remaining_limitations": (
                    ["upstream threat status remains unchanged"]
                    if mapped
                    else ["no declared check examined this threat"]
                ),
            }
        )
    return ledger
