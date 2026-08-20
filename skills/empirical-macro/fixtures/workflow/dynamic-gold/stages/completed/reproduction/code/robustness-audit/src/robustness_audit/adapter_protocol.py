"""Public protocol implemented by estimator adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from robustness_audit.subprocess_runner import CommandResult


class EstimatorAdapter(Protocol):
    def validate_baseline(self, bundle: Path) -> None: ...

    def derive_request(
        self,
        baseline: dict[str, object],
        patch: dict[str, object],
        alternative_id: str,
    ) -> dict[str, object]: ...

    def execute(
        self,
        request_path: Path,
        input_paths: dict[str, Path],
        output_dir: Path,
        timeout_seconds: float,
    ) -> CommandResult: ...

    def validate_result_bundle(self, output_dir: Path) -> None: ...
