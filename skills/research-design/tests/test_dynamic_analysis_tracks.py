from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

from research_design.pipeline import run_research_design


def _read_plan(output: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((output / "research_plan.json").read_text(encoding="utf-8")),
    )


def _read_requirements(output: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((output / "data_requirements.json").read_text(encoding="utf-8")),
    )


def _association_documents(
    intake: dict[str, object],
    request: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    association_intake = copy.deepcopy(intake)
    candidates = cast(list[dict[str, object]], association_intake["candidate_questions"])
    candidates[1].update(
        {
            "research_question": "政策利率变化后通胀的条件动态关联路径是什么？",
            "intended_claim_candidate": "associational",
            "research_family_candidate": "dynamic_shock_response",
            "risk_level": "medium",
        }
    )
    association_intake["recommended_candidate_id"] = candidates[1]["candidate_id"]

    association_request = copy.deepcopy(request)
    association_request.update(
        {
            "request_id": "rd-request-bbbbbbbbbbbbbbbb",
            "research_question": candidates[1]["research_question"],
            "intended_claim": "associational",
            "response_horizons": list(range(18)),
            "variables": [
                {
                    "variable_id": "lcpi",
                    "role": "outcome",
                    "concept": "CPI 对数水平",
                    "definition_constraints": ["季度"],
                },
                {
                    "variable_id": "dstir",
                    "role": "exposure",
                    "concept": "政策利率变化",
                    "definition_constraints": ["不得解释为外生冲击"],
                },
            ],
            "intervention_or_shock": {
                "name": "观察到的政策利率变化",
                "timing_known": True,
                "assignment_mechanism": "observational",
            },
        }
    )
    return association_intake, association_request


def test_dynamic_candidates_compile_to_distinct_analysis_tracks(
    tmp_path: Path,
    valid_intake_document: dict[str, object],
    valid_request_document: dict[str, object],
    macro_schema_path: Path,
) -> None:
    causal_request = copy.deepcopy(valid_request_document)
    causal_request["response_horizons"] = list(range(18))
    causal_request["design_audit_inputs"] = {"shock_identification": "explicit"}
    causal_request["preferred_design"] = "local_projection"
    causal_output = tmp_path / "causal"
    run_research_design(
        valid_intake_document,
        causal_request,
        causal_output,
        macro_schema_path,
    )

    association_intake, association_request = _association_documents(
        valid_intake_document,
        valid_request_document,
    )
    association_request["preferred_design"] = "conditional_projection"
    association_output = tmp_path / "association"
    run_research_design(
        association_intake,
        association_request,
        association_output,
        macro_schema_path,
    )

    causal_plan = _read_plan(causal_output)
    association_plan = _read_plan(association_output)
    assert causal_plan["analysis_track"] == "identified_shock_irf"
    assert causal_plan["primary_design"] == "local_projection"
    assert association_plan["analysis_track"] == "conditional_dynamic_association"
    assert association_plan["primary_design"] == "conditional_projection"
    assert association_plan["claim_eligibility"] == "associational_only"
    assert causal_plan["request_id"] != association_plan["request_id"]
    for output in (causal_output, association_output):
        requirements = _read_requirements(output)
        assert "research_use_mapping_unresolved" not in requirements[
            "unresolved_requirements"
        ]
