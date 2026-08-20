"""Public-CLI adapter for time-series-dynamics."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

from robustness_audit.subprocess_runner import CommandResult, run_command


def _write_json(path: Path, document: dict[str, object]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _scoped_macro_inputs(
    request_path: Path,
    input_paths: dict[str, Path],
) -> dict[str, Path]:
    request = cast(
        dict[str, object],
        json.loads(request_path.read_text(encoding="utf-8")),
    )
    macro = cast(
        dict[str, object],
        json.loads(input_paths["macro_result"].read_text(encoding="utf-8")),
    )
    if request["sample_window"] == macro["observation_period"]:
        return input_paths
    derived_macro = copy.deepcopy(macro)
    derived_macro["observation_period"] = copy.deepcopy(request["sample_window"])
    fingerprint = json.dumps(
        derived_macro,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    result_id = f"macro-result-{hashlib.sha256(fingerprint).hexdigest()[:32]}"
    derived_macro["result_id"] = result_id
    request["macro_data_bundle_refs"] = [result_id]
    derived_path = request_path.with_name(f"{result_id}.json")
    _write_json(derived_path, derived_macro)
    _write_json(request_path, request)
    return {**input_paths, "macro_result": derived_path}


class TimeSeriesAdapter:
    def __init__(
        self,
        adapter_root: Path,
        capability: dict[str, object],
    ) -> None:
        self._root = adapter_root
        self._capability = capability
        self._allowed = {
            str(item)
            for item in cast(list[object], capability["supported_patch_fields"])
        }
        schema = cast(
            dict[str, object],
            json.loads(
                (
                    adapter_root / "schemas" / "time-series-dynamics-request.schema.json"
                ).read_text(encoding="utf-8")
            ),
        )
        Draft202012Validator.check_schema(schema)
        self._request_validator = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )

    def validate_baseline(self, bundle: Path) -> None:
        result = run_command(
            ["uv", "run", "python", "scripts/validate_bundle.py", str(bundle)],
            cwd=self._root,
            timeout_seconds=60,
        )
        if result.returncode != 0:
            raise ValueError(f"baseline bundle invalid: {result.stderr or result.stdout}")

    def derive_request(
        self,
        baseline: dict[str, object],
        patch: dict[str, object],
        alternative_id: str,
    ) -> dict[str, object]:
        if fields := set(patch) - self._allowed:
            raise ValueError(
                f"adapter patch field is not allowed: {sorted(fields)[0]}"
            )
        suffix = alternative_id.removeprefix("ra-alt-")
        if len(suffix) != 32 or any(character not in "0123456789abcdef" for character in suffix):
            raise ValueError("invalid alternative_id")
        document = copy.deepcopy(baseline)
        document.update(copy.deepcopy(patch))
        document["request_id"] = f"tsd-request-{suffix}"
        self._request_validator.validate(document)
        return document

    def execute(
        self,
        request_path: Path,
        input_paths: dict[str, Path],
        output_dir: Path,
        timeout_seconds: float,
    ) -> CommandResult:
        required = {"research_plan", "macro_result", "data"}
        missing = sorted(required - input_paths.keys())
        if missing:
            raise ValueError(f"adapter input missing: {missing[0]}")
        scoped_inputs = _scoped_macro_inputs(request_path, input_paths)
        self._request_validator.validate(
            json.loads(request_path.read_text(encoding="utf-8"))
        )
        command = [
            "uv",
            "run",
            "python",
            "scripts/run_time_series_dynamics.py",
            "--request-json",
            str(request_path),
            "--research-plan-json",
            str(scoped_inputs["research_plan"]),
            "--macro-result-json",
            str(scoped_inputs["macro_result"]),
            "--data",
            str(scoped_inputs["data"]),
            "--output",
            str(output_dir),
        ]
        shock = scoped_inputs.get("shock_artifact")
        if shock is not None:
            command.extend(["--shock-artifact-json", str(shock)])
        return run_command(
            command,
            cwd=self._root,
            timeout_seconds=timeout_seconds,
        )

    def validate_result_bundle(self, output_dir: Path) -> None:
        result = run_command(
            ["uv", "run", "python", "scripts/validate_bundle.py", str(output_dir)],
            cwd=self._root,
            timeout_seconds=60,
        )
        if result.returncode != 0:
            raise ValueError(f"alternative bundle invalid: {result.stderr or result.stdout}")
