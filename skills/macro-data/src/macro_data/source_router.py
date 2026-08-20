"""Plan provider routing without silently executing fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from macro_data.source_registry import SourceRegistry


@dataclass(frozen=True)
class RoutePlan:
    primary: str
    fallback_mode: str
    fallback_candidates: list[str]
    review_required: bool


class SourceApprovalRequired(RuntimeError):
    """Raised when an official fallback requires explicit approval."""


class SourceRouter:
    def __init__(self, registry: SourceRegistry) -> None:
        self._registry = registry

    def plan(self, request: dict[str, Any]) -> RoutePlan:
        policy = request["fallback_policy"]
        primary = self._registry.primary().code
        allowed = []
        for code in policy["allowed_sources"]:
            descriptor = self._registry.get(code)
            if code != primary and descriptor is not None and descriptor.enabled:
                allowed.append(code)
        return RoutePlan(
            primary=primary,
            fallback_mode=policy["mode"],
            fallback_candidates=allowed,
            review_required=policy["mode"] == "ask" and bool(policy["allowed_sources"]),
        )

    def authorize(self, request: dict[str, Any], source: str) -> RoutePlan:
        plan = self.plan(request)
        if source == plan.primary:
            return plan
        descriptor = self._registry.get(source)
        if descriptor is None or not descriptor.enabled:
            raise ValueError(f"source is not enabled: {source}")
        if source not in plan.fallback_candidates:
            raise ValueError(f"source is not allowed by request policy: {source}")
        if plan.fallback_mode == "ask":
            raise SourceApprovalRequired(f"source requires explicit approval: {source}")
        if plan.fallback_mode not in {
            "allow_official",
            "allow_official_missing_only",
        }:
            raise ValueError(f"source fallback is disabled: {source}")
        return plan
