"""Immutable types shared by dynamic-analysis components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class DynamicsRequest:
    request_id: str
    research_plan_ref: str
    macro_data_bundle_refs: tuple[str, ...]
    shock_identification_artifact_ref: str | None
    analysis_track: str
    estimand_type: str
    method_profile: str
    outcome_variable_id: str
    exposure_variable_id: str
    control_variable_ids: tuple[str, ...]
    frequency: str
    sample_start: str
    sample_end: str
    sample_policy: str
    horizons: tuple[int, ...]
    lags: int
    hac_maxlags: int
    confidence_level: float
    claim_eligibility: str
    output_unit: str

    @classmethod
    def from_document(cls, document: dict[str, object]) -> DynamicsRequest:
        sample = cast(dict[str, object], document["sample_window"])
        horizons = tuple(
            int(value) for value in cast(list[int], document["horizons"])
        )
        if horizons != tuple(range(len(horizons))):
            raise ValueError("request horizons must be contiguous from zero")
        return cls(
            request_id=str(document["request_id"]),
            research_plan_ref=str(document["research_plan_ref"]),
            macro_data_bundle_refs=tuple(
                str(value)
                for value in cast(list[object], document["macro_data_bundle_refs"])
            ),
            shock_identification_artifact_ref=cast(
                str | None,
                document.get("shock_identification_artifact_ref"),
            ),
            analysis_track=str(document["analysis_track"]),
            estimand_type=str(document["estimand_type"]),
            method_profile=str(document["method_profile"]),
            outcome_variable_id=str(document["outcome_variable_id"]),
            exposure_variable_id=str(document["exposure_variable_id"]),
            control_variable_ids=tuple(
                str(value)
                for value in cast(list[object], document["control_variable_ids"])
            ),
            frequency=str(document["frequency"]),
            sample_start=str(sample["start"]),
            sample_end=str(sample["end"]),
            sample_policy=str(document["sample_policy"]),
            horizons=horizons,
            lags=int(cast(int, document["lags"])),
            hac_maxlags=int(cast(int, document["hac_maxlags"])),
            confidence_level=float(cast(float, document["confidence_level"])),
            claim_eligibility=str(document["claim_eligibility"]),
            output_unit=str(document["output_unit"]),
        )


@dataclass(frozen=True, slots=True)
class HorizonSample:
    horizon: int
    y: npt.NDArray[np.float64]
    x: npt.NDArray[np.float64]
    row_positions: npt.NDArray[np.int64]
    exposure_column: int
    nobs: int
    dropped_for_lags: int
    dropped_for_lead: int
    dropped_for_missing: int


@dataclass(frozen=True, slots=True)
class HorizonEstimate:
    horizon: int
    estimate: float
    standard_error: float
    confidence_lower: float
    confidence_upper: float
    nobs: int
    df_resid: float


@dataclass(frozen=True, slots=True)
class ClaimPolicy:
    analysis_track: str
    result_label: str
    claim_eligibility: str
    review_required: bool
    causal_language_allowed: bool
    title_zh: str
    required_disclaimer_zh: str
