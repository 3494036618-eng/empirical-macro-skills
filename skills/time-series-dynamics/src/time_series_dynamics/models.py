"""Immutable types shared by dynamic-analysis components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class SeriesBinding:
    variable_id: str
    series_key: str
    entity_code: str
    transform: str

    @classmethod
    def from_document(
        cls,
        document: dict[str, object],
    ) -> SeriesBinding:
        return cls(
            variable_id=str(document["variable_id"]),
            series_key=str(document["series_key"]),
            entity_code=str(document["entity_code"]),
            transform=str(document["transform"]),
        )


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
    data_profile: str = "precomputed_columns"
    response_scale: float = 100.0
    series_bindings: tuple[SeriesBinding, ...] = ()

    @classmethod
    def from_document(cls, document: dict[str, object]) -> DynamicsRequest:
        sample = cast(dict[str, object], document["sample_window"])
        horizons = tuple(int(value) for value in cast(list[int], document["horizons"]))
        if horizons != tuple(range(len(horizons))):
            raise ValueError("request horizons must be contiguous from zero")
        bindings = tuple(
            SeriesBinding.from_document(value)
            for value in cast(
                list[dict[str, object]],
                document.get("series_bindings", []),
            )
        )
        binding_ids = [binding.variable_id for binding in bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("series binding variable IDs must be unique")
        data_profile = str(document.get("data_profile", "precomputed_columns"))
        required_variables = {
            str(document["outcome_variable_id"]),
            str(document["exposure_variable_id"]),
            *(
                str(value)
                for value in cast(
                    list[object],
                    document["control_variable_ids"],
                )
            ),
        }
        if data_profile == "canonical_long_table" and not required_variables <= set(binding_ids):
            raise ValueError("series bindings do not cover request variables")
        response_scale = float(cast(float, document.get("response_scale", 100.0)))
        if response_scale <= 0:
            raise ValueError("response scale must be positive")
        return cls(
            request_id=str(document["request_id"]),
            research_plan_ref=str(document["research_plan_ref"]),
            macro_data_bundle_refs=tuple(
                str(value) for value in cast(list[object], document["macro_data_bundle_refs"])
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
                str(value) for value in cast(list[object], document["control_variable_ids"])
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
            data_profile=data_profile,
            response_scale=response_scale,
            series_bindings=bindings,
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
