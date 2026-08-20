from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from empirical_macro.models import ArtifactRef


def digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def write_validator(path: Path, *, valid: bool) -> None:
    path.write_text(
        "import json, sys\n"
        f"print(json.dumps({{'valid': {valid!r}, 'bundle': sys.argv[1]}}))\n"
        f"raise SystemExit({0 if valid else 1})\n",
        encoding="utf-8",
    )


def test_artifact_ref_requires_matching_checksum(tmp_path: Path) -> None:
    """Break caught: a changed artifact is accepted before validator execution."""
    from empirical_macro.validation import ValidatorCommand, validate_artifact_ref

    artifact = tmp_path / "bundle" / "result.json"
    artifact.parent.mkdir()
    artifact.write_text('{"valid": true}', encoding="utf-8")
    validator_script = tmp_path / "validator.py"
    write_validator(validator_script, valid=True)
    ref = ArtifactRef(
        role="macro_data",
        path="bundle/result.json",
        sha256="sha256:" + "0" * 64,
        validator="macro-data",
    )
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_artifact_ref(
            project_root=tmp_path,
            artifact_ref=ref,
            validator=ValidatorCommand(
                skill="macro-data",
                executable=sys.executable,
                script="validator.py",
            ),
        )


@pytest.mark.parametrize(
    "path",
    (
        "/tmp/result.json",
        "../result.json",
        "bundle/../../result.json",
    ),
)
def test_artifact_ref_rejects_private_or_escaping_path(
    tmp_path: Path,
    path: str,
) -> None:
    """Break caught: an Artifact ref escapes the declared project root."""
    from empirical_macro.artifact_refs import resolve_artifact_path

    with pytest.raises(ValueError, match="relative artifact path"):
        resolve_artifact_path(tmp_path, path)


def test_validator_uses_argument_array_and_parses_json(tmp_path: Path) -> None:
    """Break caught: a shell metacharacter changes the validator command."""
    from empirical_macro.validation import ValidatorCommand, validate_artifact_ref

    content = b'{"valid": true}'
    artifact = tmp_path / "bundle safe;not-a-command" / "result.json"
    artifact.parent.mkdir()
    artifact.write_bytes(content)
    validator_script = tmp_path / "validator.py"
    write_validator(validator_script, valid=True)
    ref = ArtifactRef(
        role="macro_data",
        path="bundle safe;not-a-command/result.json",
        sha256=digest(content),
        validator="macro-data",
    )
    result = validate_artifact_ref(
        project_root=tmp_path,
        artifact_ref=ref,
        validator=ValidatorCommand(
            skill="macro-data",
            executable=sys.executable,
            script="validator.py",
        ),
    )
    assert result["valid"] is True
    assert not (tmp_path / "not-a-command").exists()


def test_validator_rejection_blocks_artifact(tmp_path: Path) -> None:
    """Break caught: valid JSON with valid=false is treated as acceptance."""
    from empirical_macro.validation import ValidatorCommand, validate_artifact_ref

    content = b'{"valid": true}'
    artifact = tmp_path / "bundle" / "result.json"
    artifact.parent.mkdir()
    artifact.write_bytes(content)
    validator_script = tmp_path / "validator.py"
    write_validator(validator_script, valid=False)
    ref = ArtifactRef(
        role="macro_data",
        path="bundle/result.json",
        sha256=digest(content),
        validator="macro-data",
    )
    with pytest.raises(ValueError, match="artifact validator rejected"):
        validate_artifact_ref(
            project_root=tmp_path,
            artifact_ref=ref,
            validator=ValidatorCommand(
                skill="macro-data",
                executable=sys.executable,
                script="validator.py",
            ),
        )


def test_validator_registry_loads_all_atomic_public_validators(
    tmp_path: Path,
) -> None:
    """Break caught: production CLI runs with validators=None."""
    from empirical_macro.validation import load_validator_commands

    suite = tmp_path / "skills"
    for skill in (
        "research-design",
        "macro-data",
        "time-series-dynamics",
        "robustness-audit",
        "research-synthesis",
    ):
        script = suite / skill / "scripts" / "validate_bundle.py"
        script.parent.mkdir(parents=True)
        script.write_text("print('{}')\n", encoding="utf-8")
    commands = load_validator_commands(suite)
    assert set(commands) == {
        "research-design",
        "macro-data",
        "time-series-dynamics",
        "robustness-audit",
        "research-synthesis",
    }
    assert all(Path(command.script).is_absolute() for command in commands.values())
