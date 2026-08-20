from __future__ import annotations

from robustness_audit.threat_ledger import build_threat_ledger


def _handoff() -> dict[str, object]:
    return {
        "threats": [
            {"code": "simultaneity", "severity": "high", "status": "open"},
            {"code": "sample_selection", "severity": "medium", "status": "open"},
            {"code": "structural_break", "severity": "medium", "status": "open"},
        ]
    }


def test_ledger_never_upgrades_open_threat_to_mitigated() -> None:
    ledger = build_threat_ledger(
        _handoff(),
        [
            {
                "check_id": "ra-check-a",
                "status": "passed",
                "threat_refs": ["simultaneity"],
                "evidence_refs": ["ra-result-a"],
            }
        ],
    )

    assert ledger[0]["upstream_status"] == "open"
    assert ledger[0]["audit_status"] == "no_sensitivity_detected"
    assert "mitigated" not in ledger[0].values()
    assert ledger[1]["audit_status"] == "unexamined"


def test_ledger_distinguishes_sensitive_partial_and_unexamined() -> None:
    ledger = build_threat_ledger(
        _handoff(),
        [
            {
                "check_id": "ra-check-a",
                "status": "sensitive",
                "threat_refs": ["sample_selection"],
                "evidence_refs": [],
            },
            {
                "check_id": "ra-check-b",
                "status": "error",
                "threat_refs": ["structural_break"],
                "evidence_refs": [],
            },
        ],
    )

    statuses = {item["threat_code"]: item["audit_status"] for item in ledger}
    assert statuses == {
        "simultaneity": "unexamined",
        "sample_selection": "sensitivity_detected",
        "structural_break": "partially_examined",
    }


def test_not_applicable_only_threat_remains_unexamined() -> None:
    ledger = build_threat_ledger(
        _handoff(),
        [
            {
                "check_id": "ra-check-na",
                "status": "not_applicable",
                "threat_refs": ["simultaneity"],
                "evidence_refs": [],
            }
        ],
    )

    assert ledger[0]["audit_status"] == "unexamined"
    assert ledger[0]["executed_check_ids"] == []
