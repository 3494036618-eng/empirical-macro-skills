from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MethodFamily = Literal[
    "dynamic_shock_response",
    "conditional_dynamic_association",
    "panel_association",
    "causal_policy_evaluation",
    "forecasting_nowcasting",
    "structural_modeling",
]
RouteAction = Literal[
    "route_research_design",
    "route_macro_data",
    "route_time_series_dynamics",
    "route_robustness_audit",
    "route_research_synthesis",
    "method_not_implemented",
    "out_of_scope",
    "stopped",
    "completed",
]
WorkflowStage = Literal[
    "idea_received",
    "design_ready",
    "data_ready",
    "estimation_ready",
    "audit_ready",
    "synthesis_ready",
    "completed",
    "blocked",
    "failed",
]
WorkflowStatus = Literal["active", "blocked", "failed", "completed"]


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    method_family: MethodFamily
    executable: bool
    executor_skill: str | None
    issue_code: str | None
    user_message: str | None


@dataclass(frozen=True, slots=True)
class ResearchIntent:
    domain: str
    request_kind: str
    method_family: str | None
    has_research_plan: bool
    has_macro_data_bundle: bool
    has_estimator_bundle: bool
    has_robustness_bundle: bool
    has_workflow_state: bool


@dataclass(frozen=True, slots=True)
class RouteDecision:
    action: RouteAction
    target_skill: str | None
    issue_codes: tuple[str, ...]
    user_message: str | None


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    role: str
    path: str
    sha256: str
    validator: str


@dataclass(frozen=True, slots=True)
class WorkflowState:
    schema_version: str
    workflow_id: str
    created_at: str
    updated_at: str
    current_stage: WorkflowStage
    supported_method: str
    registry_version: str
    route_action: RouteAction
    request_id: str
    artifact_refs: tuple[ArtifactRef, ...]
    issue_codes: tuple[str, ...]
    checkpoint_id: str | None
    resume_eligible: bool
    status: WorkflowStatus


@dataclass(frozen=True, slots=True)
class Checkpoint:
    schema_version: str
    checkpoint_id: str
    workflow_id: str
    stage: WorkflowStage
    artifact_refs: tuple[ArtifactRef, ...]
    state_checksum: str
