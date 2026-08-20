"""Typed domain identities shared by research-design components."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InputMaturity(StrEnum):
    IDEA_ONLY = "idea_only"
    QUESTION_READY = "question_ready"
    DESIGN_READY = "design_ready"
    EXECUTION_READY = "execution_ready"


class FieldSource(StrEnum):
    USER_PROVIDED = "user_provided"
    INFERRED_FROM_TEXT = "inferred_from_text"
    RECOMMENDED_DEFAULT = "recommended_default"
    UNRESOLVED = "unresolved"


class FieldConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    field_path: str
    source: FieldSource
    evidence_text: str | None
    confidence: FieldConfidence
