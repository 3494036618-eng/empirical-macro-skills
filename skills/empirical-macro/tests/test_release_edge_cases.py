from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.helpers import PUBLIC_SUITE, load_contract_fixture


def test_intent_loader_accepts_valid_document_and_rejects_non_object(
    tmp_path: Path,
) -> None:
    """Break caught: the installed CLI cannot load its public intent contract."""
    from empirical_macro.intent_io import load_research_intent

    valid = tmp_path / "valid.json"
    valid.write_text(
        json.dumps(load_contract_fixture("research-intent.valid.json")),
        encoding="utf-8",
    )
    intent = load_research_intent(valid)
    assert intent.domain == "empirical_macro"
    assert intent.method_family == "conditional_dynamic_association"

    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="research intent must be an object"):
        load_research_intent(invalid)


def test_contract_loader_rejects_unknown_and_non_object_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: a missing or malformed packaged schema is silently accepted."""
    import empirical_macro.contracts as contracts

    with pytest.raises(ValueError, match="unknown contract"):
        contracts.load_schema("unknown")

    schema_root = tmp_path / "schemas"
    schema_root.mkdir()
    (schema_root / "research-intent.schema.json").write_text("[]", encoding="utf-8")
    contracts.load_schema.cache_clear()
    monkeypatch.setattr(contracts, "SCHEMA_ROOT", schema_root)
    with pytest.raises(ValueError, match="schema must be an object"):
        contracts.load_schema("research_intent")
    contracts.load_schema.cache_clear()


@pytest.mark.parametrize(
    ("document", "message"),
    (
        ([], "capability registry must be an object"),
        ({"schema_version": "wrong"}, "schema version mismatch"),
        (
            {
                "schema_version": "0.1.0-beta",
                "registry_version": "v1",
                "capabilities": {},
            },
            "coverage mismatch",
        ),
    ),
)
def test_capability_registry_rejects_malformed_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    document: object,
    message: str,
) -> None:
    """Break caught: a damaged allowlist changes executable methods."""
    import empirical_macro.capability_registry as registry

    path = tmp_path / "registry.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    registry.load_registry.cache_clear()
    monkeypatch.setattr(registry, "REGISTRY_PATH", path)
    with pytest.raises(ValueError, match=message):
        registry.load_registry()
    registry.load_registry.cache_clear()


def test_capability_registry_rejects_invalid_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: invalid executor flags are treated as executable."""
    import empirical_macro.capability_registry as registry

    base = {
        family: {"executable": False, "executor_skill": None}
        for family in registry.METHOD_FAMILIES
    }

    malformed = dict(base)
    malformed["dynamic_shock_response"] = "invalid"
    monkeypatch.setattr(
        registry,
        "load_registry",
        lambda: {"capabilities": malformed, "registry_version": "v1"},
    )
    with pytest.raises(ValueError, match="invalid capability entry"):
        registry.resolve_capability("dynamic_shock_response")

    invalid_flag = dict(base)
    invalid_flag["dynamic_shock_response"] = {
        "executable": "yes",
        "executor_skill": "time-series-dynamics",
    }
    monkeypatch.setattr(
        registry,
        "load_registry",
        lambda: {"capabilities": invalid_flag, "registry_version": "v1"},
    )
    with pytest.raises(ValueError, match="invalid executable flag"):
        registry.resolve_capability("dynamic_shock_response")

    wrong_executor = dict(base)
    wrong_executor["dynamic_shock_response"] = {
        "executable": True,
        "executor_skill": "macro-data",
    }
    monkeypatch.setattr(
        registry,
        "load_registry",
        lambda: {"capabilities": wrong_executor, "registry_version": "v1"},
    )
    with pytest.raises(ValueError, match="invalid executor skill"):
        registry.resolve_capability("dynamic_shock_response")

    unsupported_executor = dict(base)
    unsupported_executor["panel_association"] = {
        "executable": False,
        "executor_skill": "time-series-dynamics",
    }
    monkeypatch.setattr(
        registry,
        "load_registry",
        lambda: {"capabilities": unsupported_executor, "registry_version": "v1"},
    )
    with pytest.raises(ValueError, match="unsupported method has executor"):
        registry.resolve_capability("panel_association")


def test_registry_version_requires_non_empty_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: checkpoint drift protection accepts a missing registry version."""
    import empirical_macro.capability_registry as registry

    monkeypatch.setattr(registry, "load_registry", lambda: {"registry_version": ""})
    with pytest.raises(ValueError, match="registry version missing"):
        registry.registry_version()


def test_installer_rejects_linked_source_and_target(
    tmp_path: Path,
) -> None:
    """Break caught: a supposedly portable install still depends on symlinks."""
    from empirical_macro.installer import InstallTarget, install_suite

    source = tmp_path / "source"
    shutil.copytree(PUBLIC_SUITE, source)
    shutil.rmtree(source / "macro-data")
    (source / "macro-data").symlink_to(PUBLIC_SUITE / "macro-data")
    with pytest.raises(ValueError, match="invalid or linked source skill"):
        install_suite(
            source_root=source,
            target=InstallTarget(host="trae", root=tmp_path / "target"),
            dry_run=True,
        )

    target_root = tmp_path / "target-with-link"
    target_root.mkdir()
    (target_root / "linked").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="target suite contains symlink"):
        install_suite(
            source_root=PUBLIC_SUITE,
            target=InstallTarget(host="trae", root=target_root),
            dry_run=True,
        )


def test_installer_rejects_missing_or_invalid_quick_validator(
    tmp_path: Path,
) -> None:
    """Break caught: install publishes a Skill whose validator is unusable."""
    from empirical_macro.installer import InstallTarget, install_suite

    source = tmp_path / "source"
    shutil.copytree(PUBLIC_SUITE, source)
    (source / "macro-data" / "scripts" / "quick_validate.py").unlink()
    with pytest.raises(ValueError, match="quick validator missing"):
        install_suite(
            source_root=source,
            target=InstallTarget(host="trae", root=tmp_path / "missing"),
            dry_run=False,
        )

    shutil.rmtree(source)
    shutil.copytree(PUBLIC_SUITE, source)
    (source / "macro-data" / "scripts" / "quick_validate.py").write_text(
        "print('not-json')\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid JSON"):
        install_suite(
            source_root=source,
            target=InstallTarget(host="trae", root=tmp_path / "invalid"),
            dry_run=False,
        )


def test_uninstall_manifest_guards_and_dry_run(tmp_path: Path) -> None:
    """Break caught: uninstall trusts a manifest outside the target or wrong host."""
    from empirical_macro.installer import (
        MANIFEST_NAME,
        InstallTarget,
        install_suite,
        uninstall_suite,
    )

    target = InstallTarget(host="trae", root=tmp_path / "skills")
    install_suite(source_root=PUBLIC_SUITE, target=target, dry_run=False)
    manifest = target.root / MANIFEST_NAME

    with pytest.raises(ValueError, match="manifest must be inside target root"):
        uninstall_suite(
            target=target,
            manifest_path=tmp_path / "outside.json",
            dry_run=True,
        )

    wrong_host = InstallTarget(host="codex", root=target.root)
    with pytest.raises(ValueError, match="host mismatch"):
        uninstall_suite(
            target=wrong_host,
            manifest_path=manifest,
            dry_run=True,
        )

    report = uninstall_suite(
        target=target,
        manifest_path=manifest,
        dry_run=True,
    )
    assert report["dry_run"] is True
    assert manifest.is_file()


def test_public_snapshot_validator_reports_missing_files_and_symlink(
    tmp_path: Path,
) -> None:
    """Break caught: an incomplete or linked public package is marked valid."""
    from empirical_macro.public_snapshot import validate_public_snapshot

    output = tmp_path / "snapshot"
    output.mkdir()
    (output / "leak-link").symlink_to(tmp_path)
    report = validate_public_snapshot(output)
    assert report["valid"] is False
    assert "required_file_missing:README.md" in report["issue_codes"]
    assert "project_license_missing" in report["issue_codes"]
    assert "public_skill_missing:empirical-macro" in report["issue_codes"]
    assert "quick_validator_missing:empirical-macro" in report["issue_codes"]
    assert "symlink_found" in report["issue_codes"]


def test_validator_result_rejects_invalid_json_and_non_object() -> None:
    """Break caught: malformed validator output is treated as valid evidence."""
    from empirical_macro.validation import _validator_result

    with pytest.raises(ValueError, match="invalid JSON"):
        _validator_result(subprocess.CompletedProcess([], 0, stdout="{", stderr=""))
    with pytest.raises(ValueError, match="must be an object"):
        _validator_result(subprocess.CompletedProcess([], 0, stdout="[]", stderr=""))
