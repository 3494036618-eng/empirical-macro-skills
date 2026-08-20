"""Build versioned result artifacts from numerical estimates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from time_series_dynamics.claim_policy import claim_policy
from time_series_dynamics.contracts import validate_document
from time_series_dynamics.models import DynamicsRequest, HorizonEstimate


def _result_id(
    request: DynamicsRequest,
    estimates: tuple[HorizonEstimate, ...],
) -> str:
    payload = json.dumps(
        {
            "request_id": request.request_id,
            "estimates": [asdict(item) for item in estimates],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"tsd-result-{hashlib.sha256(payload).hexdigest()[:32]}"


def build_result(
    request: DynamicsRequest,
    estimates: tuple[HorizonEstimate, ...],
) -> dict[str, object]:
    if not estimates:
        raise ValueError("result requires at least one horizon estimate")
    policy = claim_policy(request.analysis_track)
    if request.estimand_type != policy.result_label:
        raise ValueError("request estimand does not match claim policy")
    if request.claim_eligibility != policy.claim_eligibility:
        raise ValueError("request claim does not match claim policy")
    if tuple(item.horizon for item in estimates) != request.horizons:
        raise ValueError("estimated horizons do not match request")
    document: dict[str, object] = {
        "schema_version": "0.1.0",
        "result_id": _result_id(request, estimates),
        "request_id": request.request_id,
        "analysis_track": request.analysis_track,
        "estimand_type": policy.result_label,
        "claim_eligibility": policy.claim_eligibility,
        "review_required": policy.review_required,
        "causal_language_allowed": policy.causal_language_allowed,
        "execution_status": "success",
        "interval_scope": "pointwise",
        "horizon_results": [
            {
                **asdict(item),
                "confidence_level": request.confidence_level,
            }
            for item in estimates
        ],
    }
    validate_document("result", document)
    return document
