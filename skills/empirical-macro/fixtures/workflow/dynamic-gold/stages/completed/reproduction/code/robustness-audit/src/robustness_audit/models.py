"""Immutable contract models for robustness-audit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in cast(list[object], value))


def _patch_tuple(value: object) -> tuple[tuple[str, object], ...]:
    patch = cast(dict[str, object], value)
    return tuple(sorted(patch.items()))


@dataclass(frozen=True, slots=True)
class AuditCheckSpec:
    check_id: str
    check_family: str
    required: bool
    same_estimand_required: bool
    anchor_horizons: tuple[int, ...]
    metric_names: tuple[str, ...]
    decision_rule_ids: tuple[str, ...]
    failure_policy: str
    uses_randomness: bool

    @classmethod
    def from_document(cls, document: dict[str, object]) -> AuditCheckSpec:
        return cls(
            check_id=str(document["check_id"]),
            check_family=str(document["check_family"]),
            required=bool(document["required"]),
            same_estimand_required=bool(document["same_estimand_required"]),
            anchor_horizons=tuple(
                int(item) for item in cast(list[int], document["anchor_horizons"])
            ),
            metric_names=_string_tuple(document["metrics"]),
            decision_rule_ids=_string_tuple(document["decision_rule_ids"]),
            failure_policy=str(document["failure_policy"]),
            uses_randomness=bool(document["uses_randomness"]),
        )


@dataclass(frozen=True, slots=True)
class AuditAlternativeSpec:
    alternative_id: str
    check_id: str
    patch: tuple[tuple[str, object], ...]

    @classmethod
    def from_document(cls, document: dict[str, object]) -> AuditAlternativeSpec:
        return cls(
            alternative_id=str(document["alternative_id"]),
            check_id=str(document["check_id"]),
            patch=_patch_tuple(document["patch"]),
        )


@dataclass(frozen=True, slots=True)
class AuditPlan:
    audit_plan_id: str
    audit_request_id: str
    adapter_id: str
    baseline_request_ref: str
    estimand_fingerprint: str
    analysis_track: str
    claim_eligibility: str
    plan_timing: str
    checks: tuple[AuditCheckSpec, ...]
    alternatives: tuple[AuditAlternativeSpec, ...]
    max_variants: int
    max_runtime_seconds: int
    max_parallel_jobs: int
    random_seed: int | None

    @classmethod
    def from_document(cls, document: dict[str, object]) -> AuditPlan:
        budget = cast(dict[str, object], document["execution_budget"])
        randomness = cast(dict[str, object], document["randomness"])
        seed = randomness.get("seed")
        return cls(
            audit_plan_id=str(document["audit_plan_id"]),
            audit_request_id=str(document["audit_request_id"]),
            adapter_id=str(document["adapter_id"]),
            baseline_request_ref=str(document["baseline_request_ref"]),
            estimand_fingerprint=str(document["baseline_estimand_fingerprint"]),
            analysis_track=str(document["analysis_track"]),
            claim_eligibility=str(document["claim_eligibility"]),
            plan_timing=str(document["plan_timing"]),
            checks=tuple(
                AuditCheckSpec.from_document(cast(dict[str, object], item))
                for item in cast(list[object], document["checks"])
            ),
            alternatives=tuple(
                AuditAlternativeSpec.from_document(cast(dict[str, object], item))
                for item in cast(list[object], document["alternatives"])
            ),
            max_variants=int(cast(int, budget["max_variants"])),
            max_runtime_seconds=int(cast(int, budget["max_runtime_seconds"])),
            max_parallel_jobs=int(cast(int, budget["max_parallel_jobs"])),
            random_seed=int(seed) if isinstance(seed, int) else None,
        )
