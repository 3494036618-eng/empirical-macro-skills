from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import PUBLIC_SUITE

EXPECTED_SKILLS = [
    "empirical-macro",
    "macro-data",
    "research-design",
    "research-synthesis",
    "robustness-audit",
    "time-series-dynamics",
]


@pytest.mark.parametrize(
    ("host", "relative_root"),
    (
        ("generic", "custom-agent/skills"),
        ("trae", ".trae/skills"),
        ("codex", ".agents/skills"),
        ("claude-code", ".claude/skills"),
    ),
)
def test_fresh_install_copies_all_six_skills(
    tmp_path: Path,
    host: str,
    relative_root: str,
) -> None:
    """Break caught: a host receives an incomplete or linked Skill suite."""
    from empirical_macro.installer import InstallTarget, install_suite

    target = InstallTarget(host=host, root=tmp_path / relative_root)
    report = install_suite(
        source_root=PUBLIC_SUITE,
        target=target,
        dry_run=False,
    )
    assert report["installed_skills"] == EXPECTED_SKILLS
    assert all(
        (target.root / skill / "SKILL.md").is_file()
        and not (target.root / skill).is_symlink()
        for skill in EXPECTED_SKILLS
    )
    assert (target.root / "empirical-macro-install-manifest.json").is_file()


def test_fresh_install_rejects_unmanaged_target_file(tmp_path: Path) -> None:
    """Break caught: installation overwrites a pre-existing user Skill."""
    from empirical_macro.installer import InstallTarget, install_suite

    target = InstallTarget(host="trae", root=tmp_path / ".trae" / "skills")
    existing = target.root / "empirical-macro" / "SKILL.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("user content", encoding="utf-8")
    with pytest.raises(ValueError, match="unmanaged target file"):
        install_suite(
            source_root=PUBLIC_SUITE,
            target=target,
            dry_run=False,
        )
    assert existing.read_text(encoding="utf-8") == "user content"


def test_source_inventory_ignores_uv_runtime_environment(tmp_path: Path) -> None:
    """Break caught: running the documented uv command poisons source discovery."""
    from empirical_macro.installer import _source_files

    source = tmp_path / "public-suite"
    shutil.copytree(PUBLIC_SUITE, source)
    runtime = source / "empirical-macro" / ".venv"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin" / "python").symlink_to(sys.executable)
    (runtime / "pyvenv.cfg").write_text("managed\n", encoding="utf-8")

    entries = _source_files(source)

    assert entries
    assert not any("/.venv/" in entry.relative_path for entry in entries)


def test_prepare_runtime_uses_locked_noneditable_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: installation validates with an unrelated Python runtime."""
    import empirical_macro.runtime_environment as runtime_environment

    skill = tmp_path / "time-series-dynamics"
    skill.mkdir()
    (skill / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (skill / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    observed: list[str] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        observed.extend(command)
        python = skill / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        runtime_environment.shutil,
        "which",
        lambda _: "/usr/local/bin/uv",
    )
    monkeypatch.setattr(runtime_environment.subprocess, "run", fake_run)

    assert runtime_environment.prepare_runtime(skill) == (
        skill / ".venv" / "bin" / "python"
    )
    assert "--locked" in observed
    assert "--no-dev" in observed
    assert "--no-editable" in observed
    assert runtime_environment.managed_runtime(skill) is True


def test_prepare_runtime_requires_uv_for_project_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: dependency setup silently falls back to the host Python."""
    import empirical_macro.runtime_environment as runtime_environment

    skill = tmp_path / "macro-data"
    skill.mkdir()
    (skill / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (skill / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    monkeypatch.setattr(runtime_environment.shutil, "which", lambda _: None)

    with pytest.raises(ValueError, match="uv is required"):
        runtime_environment.prepare_runtime(skill)


def test_upgrade_replaces_only_unchanged_managed_files(tmp_path: Path) -> None:
    """Break caught: upgrade ignores manifest ownership and user edits."""
    from empirical_macro.installer import InstallTarget, install_suite

    source = tmp_path / "source"
    shutil.copytree(PUBLIC_SUITE, source)
    target = InstallTarget(host="codex", root=tmp_path / ".agents" / "skills")
    install_suite(source_root=source, target=target, dry_run=False)
    source_skill = source / "empirical-macro" / "SKILL.md"
    source_skill.write_text(
        source_skill.read_text(encoding="utf-8") + "\nupgrade\n",
        encoding="utf-8",
    )
    install_suite(source_root=source, target=target, dry_run=False)
    assert (target.root / "empirical-macro" / "SKILL.md").read_text(
        encoding="utf-8"
    ).endswith("upgrade\n")

    managed = target.root / "macro-data" / "SKILL.md"
    managed.write_text("user modified managed file", encoding="utf-8")
    with pytest.raises(ValueError, match="managed target file changed"):
        install_suite(source_root=source, target=target, dry_run=False)


def test_uninstall_preserves_user_files_and_modified_managed_files(
    tmp_path: Path,
) -> None:
    """Break caught: uninstall removes files not owned by its manifest."""
    from empirical_macro.installer import (
        InstallTarget,
        install_suite,
        uninstall_suite,
    )

    target = InstallTarget(host="claude-code", root=tmp_path / ".claude" / "skills")
    install_suite(source_root=PUBLIC_SUITE, target=target, dry_run=False)
    user_file = target.root / "empirical-macro" / "user-notes.md"
    user_file.write_text("keep", encoding="utf-8")
    modified = target.root / "macro-data" / "SKILL.md"
    modified.write_text("keep modified", encoding="utf-8")
    manifest = target.root / "empirical-macro-install-manifest.json"

    report = uninstall_suite(
        target=target,
        manifest_path=manifest,
        dry_run=False,
    )
    assert user_file.read_text(encoding="utf-8") == "keep"
    assert modified.read_text(encoding="utf-8") == "keep modified"
    assert "macro-data/SKILL.md" in report["retained_modified_files"]
    assert not manifest.exists()


def test_uninstall_removes_installer_managed_runtime(tmp_path: Path) -> None:
    """Break caught: uninstall leaves a generated dependency environment."""
    from empirical_macro.installer import (
        MANIFEST_NAME,
        InstallTarget,
        install_suite,
        uninstall_suite,
    )
    from empirical_macro.runtime_environment import (
        RUNTIME_MARKER,
        RUNTIME_MARKER_CONTENT,
    )

    target = InstallTarget(host="trae", root=tmp_path / ".trae" / "skills")
    install_suite(source_root=PUBLIC_SUITE, target=target, dry_run=False)
    runtime = target.root / "time-series-dynamics" / ".venv"
    runtime.mkdir()
    (runtime / RUNTIME_MARKER).write_text(
        RUNTIME_MARKER_CONTENT,
        encoding="utf-8",
    )
    (runtime / "dependency.txt").write_text("managed", encoding="utf-8")

    report = uninstall_suite(
        target=target,
        manifest_path=target.root / MANIFEST_NAME,
        dry_run=False,
    )

    assert "time-series-dynamics/.venv" in report["removed_runtime_environments"]
    assert not runtime.exists()


def test_dry_run_has_no_filesystem_side_effect(tmp_path: Path) -> None:
    """Break caught: installation preview mutates the target."""
    from empirical_macro.installer import InstallTarget, install_suite

    target = InstallTarget(host="trae", root=tmp_path / ".trae" / "skills")
    report = install_suite(
        source_root=PUBLIC_SUITE,
        target=target,
        dry_run=True,
    )
    assert report["dry_run"] is True
    assert not target.root.exists()


def test_installer_cli_dry_run_is_structured_and_read_only(tmp_path: Path) -> None:
    """Break caught: the public installer CLI ignores preview mode."""
    target = tmp_path / ".trae" / "skills"
    completed = subprocess.run(
        [
            sys.executable,
            str(PUBLIC_SUITE.parents[2] / "scripts" / "install_skill_suite.py"),
            "install",
            "--source-root",
            str(PUBLIC_SUITE),
            "--host",
            "trae",
            "--target-root",
            str(target),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert '"dry_run": true' in completed.stdout
    assert not target.exists()


def test_install_aborts_when_target_changes_during_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: an install overwrites a concurrent user file change."""
    import empirical_macro.installer as installer
    from empirical_macro.installer import InstallTarget, install_suite

    target = InstallTarget(host="trae", root=tmp_path / ".trae" / "skills")
    target.root.mkdir(parents=True)
    user_file = target.root / "user-skill" / "notes.txt"
    user_file.parent.mkdir()
    user_file.write_text("before", encoding="utf-8")
    original = installer._run_quick_validators

    def mutate_target(staging: Path) -> None:
        original(staging)
        user_file.write_text("changed during install", encoding="utf-8")

    monkeypatch.setattr(installer, "_run_quick_validators", mutate_target)
    with pytest.raises(ValueError, match="target changed during install"):
        install_suite(
            source_root=PUBLIC_SUITE,
            target=target,
            dry_run=False,
        )
    assert user_file.read_text(encoding="utf-8") == "changed during install"


def test_install_rechecks_target_inside_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: a change after pre-publish fingerprint is overwritten."""
    import empirical_macro.installer as installer
    from empirical_macro.installer import InstallTarget, install_suite

    target = InstallTarget(host="trae", root=tmp_path / ".trae" / "skills")
    target.root.mkdir(parents=True)
    user_file = target.root / "user-skill" / "notes.txt"
    user_file.parent.mkdir()
    user_file.write_text("before", encoding="utf-8")
    original = installer._publish

    def mutate_target(staging: Path, destination: Path, *args: object) -> None:
        user_file.write_text("changed at publish", encoding="utf-8")
        original(staging, destination, *args)

    monkeypatch.setattr(installer, "_publish", mutate_target)
    with pytest.raises(ValueError, match="target changed during install"):
        install_suite(
            source_root=PUBLIC_SUITE,
            target=target,
            dry_run=False,
        )
    assert user_file.read_text(encoding="utf-8") == "changed at publish"


def test_uninstall_rejects_manifest_path_not_owned_by_declared_skill(
    tmp_path: Path,
) -> None:
    """Break caught: a forged manifest claims and deletes a user file."""
    from empirical_macro.installer import (
        MANIFEST_NAME,
        InstallTarget,
        install_suite,
        uninstall_suite,
    )

    target = InstallTarget(host="trae", root=tmp_path / ".trae" / "skills")
    install_suite(source_root=PUBLIC_SUITE, target=target, dry_run=False)
    user_file = target.root / "user-owned.txt"
    user_file.write_text("keep", encoding="utf-8")
    manifest_path = target.root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "user-owned.txt"
    manifest["files"][0]["sha256"] = (
        "sha256:" + hashlib.sha256(user_file.read_bytes()).hexdigest()
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest path does not belong to skill"):
        uninstall_suite(
            target=target,
            manifest_path=manifest_path,
            dry_run=False,
        )
    assert user_file.read_text(encoding="utf-8") == "keep"


def test_uninstall_rechecks_file_after_candidate_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Break caught: a concurrent user edit is deleted after an earlier hash."""
    import empirical_macro.installer as installer
    from empirical_macro.installer import (
        MANIFEST_NAME,
        InstallTarget,
        install_suite,
        uninstall_suite,
    )

    target = InstallTarget(host="trae", root=tmp_path / ".trae" / "skills")
    install_suite(source_root=PUBLIC_SUITE, target=target, dry_run=False)
    managed = target.root / "empirical-macro" / "SKILL.md"
    original = installer._uninstall_candidates

    def mutate_after_collection(
        target_root: Path,
        files: list[dict[str, object]],
    ) -> tuple[list[Path], list[str]]:
        result = original(target_root, files)
        managed.write_text("concurrent edit", encoding="utf-8")
        return result

    monkeypatch.setattr(installer, "_uninstall_candidates", mutate_after_collection)
    report = uninstall_suite(
        target=target,
        manifest_path=target.root / MANIFEST_NAME,
        dry_run=False,
    )
    assert managed.read_text(encoding="utf-8") == "concurrent edit"
    assert "empirical-macro/SKILL.md" in report["retained_modified_files"]
