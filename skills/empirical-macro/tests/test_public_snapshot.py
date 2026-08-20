from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[4]
EXPECTED_SKILLS = {
    "empirical-macro",
    "macro-data",
    "research-design",
    "research-synthesis",
    "robustness-audit",
    "time-series-dynamics",
}


def test_public_snapshot_excludes_restricted_and_internal_files(
    tmp_path: Path,
) -> None:
    """Break caught: the public package includes internal or restricted data."""
    from empirical_macro.public_snapshot import build_public_snapshot

    output = tmp_path / "public"
    build_public_snapshot(project_root=PROJECT_ROOT, output_dir=output)
    names = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    }
    assert not any("sanitized-live" in name for name in names)
    assert not any("验收与发布" in name for name in names)
    assert not any("agent-runs" in name for name in names)
    assert not any(name.endswith(".env") for name in names)
    assert not any("/open_source/" in name for name in names)
    assert "skills/empirical-macro/INSTALL.md" not in names
    assert "INSTALL.md" in names
    assert {"README.md", "SECURITY.md", "CONTRIBUTING.md", "plugin.json"} <= names
    readme = (output / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# 宏观经济实证研究 Skills")
    assert "# 学科数据 Skill" not in readme
    assert {path.name for path in (output / "skills").iterdir()} == EXPECTED_SKILLS
    assert not any(path.is_symlink() for path in output.rglob("*"))


@pytest.mark.parametrize(
    ("payload", "issue_code"),
    (
        ("/" + "Users/example/private/file", "private_path_found"),
        ("/" + "home/example/private/file", "private_path_found"),
        ("/" + "private/var/example/file", "private_path_found"),
        ("ark-" + "example-secret-value", "secret_value_found"),
        ("Bearer " + "abcdefghijklmnop", "secret_value_found"),
        ("Authorization:" + " abcdefghijklmnop", "secret_value_found"),
        ('{"trace_' + 'id": "trace-sensitive-value"}', "raw_trace_id_found"),
        ("byte" + "dance", "private_workspace_term_found"),
        ("owner" + "@example.com", "email_address_found"),
    ),
)
def test_public_snapshot_validator_rejects_private_or_secret_values(
    tmp_path: Path,
    payload: str,
    issue_code: str,
) -> None:
    """Break caught: a clean snapshot validator misses a release secret."""
    from empirical_macro.public_snapshot import (
        build_public_snapshot,
        validate_public_snapshot,
    )

    output = tmp_path / "public"
    build_public_snapshot(project_root=PROJECT_ROOT, output_dir=output)
    (output / "leak.txt").write_text(payload, encoding="utf-8")
    report = validate_public_snapshot(output)
    assert report["valid"] is False
    assert issue_code in report["issue_codes"]


def test_public_snapshot_contains_owner_approved_license(tmp_path: Path) -> None:
    """Break caught: the approved project license is omitted from publication."""
    from empirical_macro.public_snapshot import (
        build_public_snapshot,
        validate_public_snapshot,
    )

    output = tmp_path / "public"
    build_public_snapshot(project_root=PROJECT_ROOT, output_dir=output)
    report = validate_public_snapshot(output)
    assert report["valid"] is True
    assert report["issue_codes"] == []
    assert (output / "LICENSE").read_bytes() == (
        PROJECT_ROOT / "LICENSE"
    ).read_bytes()


@pytest.mark.parametrize("existing_output", (False, True))
def test_public_snapshot_keeps_missing_license_as_owner_gate(
    tmp_path: Path,
    existing_output: bool,
) -> None:
    """Break caught: an unlicensed project bypasses or destroys the owner gate."""
    from empirical_macro.public_snapshot import build_public_snapshot

    project = tmp_path / "project"
    module = project / "30_宏观经济实证Skill" / "02_模块开发"
    project.mkdir()
    (project / "README.md").write_text("public project", encoding="utf-8")
    for skill in EXPECTED_SKILLS:
        skill_root = module / skill
        (skill_root / "scripts").mkdir(parents=True)
        (skill_root / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")
        (skill_root / "scripts" / "quick_validate.py").write_text(
            "raise SystemExit(0)\n",
            encoding="utf-8",
        )
    empirical = module / "empirical-macro"
    (empirical / "THIRD_PARTY_NOTICES.md").write_text(
        "No third-party notices.\n",
        encoding="utf-8",
    )
    (empirical / "INSTALL.md").write_text(
        "# Install\n",
        encoding="utf-8",
    )
    open_source = empirical / "open_source"
    (open_source / "scripts").mkdir(parents=True)
    for name in ("README.md", "SECURITY.md", "CONTRIBUTING.md"):
        (open_source / name).write_text(f"# {name}\n", encoding="utf-8")
    (open_source / "scripts" / "scan_public_release.py").write_text(
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    (open_source / "plugin.json").write_text(
        '{"name":"empirical-macro-skills",'
        '"version":"0.1.0-beta","license":"Apache-2.0"}\n',
        encoding="utf-8",
    )
    stages = empirical / "fixtures" / "workflow" / "dynamic-gold" / "stages"
    (stages / "design_ready").mkdir(parents=True)
    (stages / "data_ready").mkdir(parents=True)
    (stages / "design_ready" / "manifest.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (stages / "data_ready" / "manifest.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    output = tmp_path / "snapshot"
    if existing_output:
        output.mkdir()
        (output / "last-valid.txt").write_text("preserve", encoding="utf-8")

    report = build_public_snapshot(project_root=project, output_dir=output)

    assert report["valid"] is False
    assert report["issue_codes"] == ["project_license_missing"]
    assert report["published"] is not existing_output
    if existing_output:
        assert (output / "last-valid.txt").read_text(encoding="utf-8") == "preserve"
    else:
        assert output.is_dir()


def test_public_snapshot_contains_portable_quick_validation_inputs(
    tmp_path: Path,
) -> None:
    """Break caught: installed atomic quick validators lose public evidence."""
    from empirical_macro.public_snapshot import build_public_snapshot

    output = tmp_path / "public"
    build_public_snapshot(project_root=PROJECT_ROOT, output_dir=output)
    assert (
        output
        / "skills"
        / "research-design"
        / "fixtures"
        / "public"
        / "jel-example5-design"
        / "research-design-run-manifest.json"
    ).is_file()
    assert (
        output
        / "skills"
        / "time-series-dynamics"
        / "fixtures"
        / "public"
        / "jel-example5-input-evidence"
        / "input-evidence-manifest.json"
    ).is_file()


def test_public_snapshot_rejects_output_overlapping_source_tree(
    tmp_path: Path,
) -> None:
    """Break caught: snapshot publication can replace the source project."""
    from empirical_macro.public_snapshot import build_public_snapshot

    project = tmp_path / "project"
    module = project / "30_宏观经济实证Skill" / "02_模块开发"
    module.mkdir(parents=True)
    with pytest.raises(ValueError, match="snapshot output overlaps source"):
        build_public_snapshot(project_root=project, output_dir=project)
    with pytest.raises(ValueError, match="snapshot output overlaps source"):
        build_public_snapshot(project_root=project, output_dir=module / "snapshot")


@pytest.mark.parametrize(
    "name",
    (
        ".env.local",
        ".env.production",
        "private.pem",
        "credentials.p12",
        "credentials.json",
        ".netrc",
    ),
)
def test_public_snapshot_excludes_credential_file_names(name: str) -> None:
    """Break caught: credential files are copied without content scanning."""
    from empirical_macro.public_snapshot import _excluded

    assert _excluded(Path(name)) is True


def test_public_snapshot_rejects_output_file_inside_project(
    tmp_path: Path,
) -> None:
    """Break caught: publication replaces the project README with a directory."""
    from empirical_macro.public_snapshot import build_public_snapshot

    project = tmp_path / "project"
    module = project / "30_宏观经济实证Skill" / "02_模块开发"
    module.mkdir(parents=True)
    readme = project / "README.md"
    readme.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="snapshot output must be a directory"):
        build_public_snapshot(project_root=project, output_dir=readme)
    assert readme.read_text(encoding="utf-8") == "keep"


def test_snapshot_scanner_rejects_explicit_cloud_secret(tmp_path: Path) -> None:
    """Break caught: a credential assignment is published as ordinary JSON."""
    from empirical_macro.public_snapshot import _scan_file

    secret = "abcd" + "efghijklmnopqrstuvwx"
    path = tmp_path / "config.json"
    path.write_text(
        '{"aws_' + 'secret_access_key": "' + secret + '"}',
        encoding="utf-8",
    )
    assert "secret_value_found" in _scan_file(path)


def test_snapshot_build_cli_returns_zero_for_approved_license(
    tmp_path: Path,
) -> None:
    """Break caught: a valid licensed snapshot fails the release pipeline."""
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "snapshot"
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "build_public_snapshot.py"),
            "--project-root",
            str(PROJECT_ROOT),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert output.is_dir()
    assert (output / "LICENSE").is_file()


def test_valid_snapshot_replaces_existing_output(
    tmp_path: Path,
) -> None:
    """Break caught: a valid release cannot atomically replace an old snapshot."""
    from empirical_macro.public_snapshot import build_public_snapshot

    output = tmp_path / "snapshot"
    output.mkdir()
    sentinel = output / "last-valid.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    report = build_public_snapshot(
        project_root=PROJECT_ROOT,
        output_dir=output,
    )
    assert report["valid"] is True
    assert report["published"] is True
    assert not sentinel.exists()
    assert (output / "LICENSE").is_file()


def test_public_validation_artifacts_reject_source_symlink(
    tmp_path: Path,
) -> None:
    """Break caught: copytree dereferences a private file into the snapshot."""
    from empirical_macro.public_snapshot import _copy_public_validation_artifacts

    empirical = tmp_path / "empirical"
    stages = empirical / "fixtures" / "workflow" / "dynamic-gold" / "stages"
    design = stages / "design_ready"
    data = stages / "data_ready"
    design.mkdir(parents=True)
    data.mkdir(parents=True)
    (data / "manifest.json").write_text("{}", encoding="utf-8")
    private = tmp_path / "private.txt"
    private.write_text("sensitive", encoding="utf-8")
    (design / "leak.txt").symlink_to(private)

    with pytest.raises(ValueError, match="validation artifacts contain symlink"):
        _copy_public_validation_artifacts(empirical, tmp_path / "skills")
