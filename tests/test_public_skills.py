# ruff: noqa: S101

from __future__ import annotations

from pathlib import Path

from empirical_macro.public_snapshot import validate_public_snapshot

SKILLS = (
    "empirical-macro",
    "macro-data",
    "research-design",
    "research-synthesis",
    "robustness-audit",
    "time-series-dynamics",
)

IGNORED_DIRECTORY_NAMES = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
}


def _public_files(skill: Path) -> list[Path]:
    return [
        path
        for path in skill.rglob("*")
        if path.is_file()
        and not any(part in IGNORED_DIRECTORY_NAMES for part in path.parts)
    ]


def test_installable_skills_are_bounded_and_have_entry_points() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in SKILLS:
        skill = root / "skills" / name
        assert (skill / "SKILL.md").is_file()
        assert (skill / "kernel.py").is_file()
        assert len(_public_files(skill)) <= 256
        assert not (skill / "tests").exists()


def test_ci_keeps_uv_environment_outside_the_skill_tree() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "validate.yml").read_text("utf-8")

    assert "UV_PROJECT_ENVIRONMENT=${{ runner.temp }}/" in workflow
    assert "--project skills/macro-data" in workflow
    assert "pytest -o addopts='--strict-markers' tests" in workflow
    assert "actions/setup-node@v4" in workflow
    assert 'node-version: "20"' in workflow
    assert "uvx --from skills-ref agentskills validate" in workflow


def test_public_snapshot_rejects_local_openai4s_compatibility_code(
    tmp_path: Path,
) -> None:
    (tmp_path / "openai4s_local_adapter.py").write_text(
        "LOCAL_ONLY = True\n",
        encoding="utf-8",
    )

    report = validate_public_snapshot(tmp_path)

    assert "forbidden_public_path" in report["issue_codes"]


def test_public_snapshot_requires_the_npm_entry_files(tmp_path: Path) -> None:
    report = validate_public_snapshot(tmp_path)

    assert "required_file_missing:.npmignore" in report["issue_codes"]
    assert "required_file_missing:package.json" in report["issue_codes"]
    assert (
        "required_file_missing:bin/empirical-macro-skills.mjs"
        in report["issue_codes"]
    )


def test_readme_describes_the_project_without_internal_acceptance_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text("utf-8")
    forbidden = (
        "Agent Skills 参考实现",
        "短窗口验证",
        "104 条候选记录",
        "24 条目标",
        "has passed privacy scanning",
        "pending and is not claimed",
    )

    assert "本项目是一套面向宏观经济实证研究的 Agent Skill 套件" in readme
    assert not any(phrase in readme for phrase in forbidden)


def test_internal_release_documents_are_not_public() -> None:
    root = Path(__file__).resolve().parents[1]
    internal_documents = (
        "HOST_ADAPTER_ARCHITECTURE.md",
        "OPEN_SOURCE_RELEASE_IMPLEMENTATION_PLAN.md",
        "PUBLICATION_CHECKLIST.md",
    )

    for name in internal_documents:
        assert not (root / "docs" / name).exists()
