from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast
from uuid import uuid4

from empirical_macro.artifact_refs import resolve_artifact_path, sha256_file
from empirical_macro.contracts import SCHEMA_VERSION, validate_document
from empirical_macro.models import (
    ArtifactRef,
    Checkpoint,
    RouteAction,
    WorkflowStage,
    WorkflowState,
    WorkflowStatus,
)
from empirical_macro.validation import ValidatorCommand, validate_artifact_ref

CHECKPOINT_STAGES = frozenset(
    {
        "design_ready",
        "data_ready",
        "estimation_ready",
        "audit_ready",
        "synthesis_ready",
        "completed",
    }
)
REQUIRED_STAGE_VALIDATORS: dict[WorkflowStage, frozenset[str]] = {
    "design_ready": frozenset({"research-design"}),
    "data_ready": frozenset({"research-design", "macro-data"}),
    "estimation_ready": frozenset(
        {"research-design", "macro-data", "time-series-dynamics"}
    ),
    "audit_ready": frozenset(
        {
            "research-design",
            "macro-data",
            "time-series-dynamics",
            "robustness-audit",
        }
    ),
    "synthesis_ready": frozenset(
        {
            "research-design",
            "macro-data",
            "time-series-dynamics",
            "robustness-audit",
        }
    ),
    "completed": frozenset(
        {
            "research-design",
            "macro-data",
            "time-series-dynamics",
            "robustness-audit",
            "research-synthesis",
        }
    ),
}


def state_to_document(state: WorkflowState) -> dict[str, object]:
    document = json.loads(
        json.dumps(asdict(state), ensure_ascii=False, separators=(",", ":"))
    )
    return cast(dict[str, object], document)


def state_from_document(document: dict[str, object]) -> WorkflowState:
    refs = tuple(
        ArtifactRef(
            role=cast(str, item["role"]),
            path=cast(str, item["path"]),
            sha256=cast(str, item["sha256"]),
            validator=cast(str, item["validator"]),
        )
        for item in cast(list[dict[str, object]], document["artifact_refs"])
    )
    return WorkflowState(
        schema_version=cast(str, document["schema_version"]),
        workflow_id=cast(str, document["workflow_id"]),
        created_at=cast(str, document["created_at"]),
        updated_at=cast(str, document["updated_at"]),
        current_stage=cast(WorkflowStage, document["current_stage"]),
        supported_method=cast(str, document["supported_method"]),
        registry_version=cast(str, document["registry_version"]),
        route_action=cast(RouteAction, document["route_action"]),
        request_id=cast(str, document["request_id"]),
        artifact_refs=refs,
        issue_codes=tuple(cast(list[str], document["issue_codes"])),
        checkpoint_id=cast(str | None, document["checkpoint_id"]),
        resume_eligible=cast(bool, document["resume_eligible"]),
        status=cast(WorkflowStatus, document["status"]),
    )


def _canonical_state(state: WorkflowState) -> bytes:
    document = state_to_document(state)
    document["checkpoint_id"] = None
    document.pop("updated_at")
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def create_checkpoint(state: WorkflowState) -> Checkpoint:
    if state.current_stage not in CHECKPOINT_STAGES or not state.artifact_refs:
        raise ValueError(f"stage is not checkpoint eligible: {state.current_stage}")
    observed = {ref.validator for ref in state.artifact_refs}
    required = REQUIRED_STAGE_VALIDATORS[state.current_stage]
    if not required.issubset(observed):
        missing = ",".join(sorted(required - observed))
        raise ValueError(f"stage evidence incomplete: {missing}")
    state_checksum = "sha256:" + hashlib.sha256(_canonical_state(state)).hexdigest()
    identity = f"{state.workflow_id}:{state.current_stage}:{state_checksum}".encode()
    checkpoint_id = "checkpoint-" + hashlib.sha256(identity).hexdigest()[:32]
    return Checkpoint(
        schema_version=SCHEMA_VERSION,
        checkpoint_id=checkpoint_id,
        workflow_id=state.workflow_id,
        stage=state.current_stage,
        artifact_refs=state.artifact_refs,
        state_checksum=state_checksum,
    )


def prepare_state_for_persistence(state: WorkflowState) -> WorkflowState:
    if state.status != "active" or not state.resume_eligible:
        return state
    checkpoint = create_checkpoint(state)
    return replace(state, checkpoint_id=checkpoint.checkpoint_id)


def write_state_transactionally(state: WorkflowState, path: Path) -> None:
    document = state_to_document(state)
    validate_document("workflow_state", document)
    payload = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.staging-{uuid4().hex}")
    try:
        with staging.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise


def resume_workflow(
    *,
    state_path: Path,
    project_root: Path,
    registry_version: str,
    validators: Mapping[str, ValidatorCommand] | None = None,
) -> WorkflowState:
    document = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("workflow state must be an object")
    state_document = cast(dict[str, object], document)
    validate_document("workflow_state", state_document)
    state = state_from_document(state_document)
    if state.registry_version != registry_version:
        raise ValueError("registry version mismatch")
    if state.status != "active" or not state.resume_eligible:
        raise ValueError("workflow state is not resume eligible")
    checkpoint = create_checkpoint(state)
    if state.checkpoint_id != checkpoint.checkpoint_id:
        raise ValueError("checkpoint identity mismatch")
    for artifact_ref in state.artifact_refs:
        path = resolve_artifact_path(project_root, artifact_ref.path)
        if sha256_file(path) != artifact_ref.sha256:
            raise ValueError(f"checksum mismatch: {artifact_ref.path}")
    if validators is None:
        raise ValueError("validator commands are required")
    for artifact_ref in state.artifact_refs:
        command = validators.get(artifact_ref.validator)
        if command is None:
            raise ValueError(f"validator command missing: {artifact_ref.validator}")
        validate_artifact_ref(
            project_root=project_root,
            artifact_ref=artifact_ref,
            validator=command,
        )
    return state
