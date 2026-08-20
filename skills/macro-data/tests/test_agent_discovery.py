from conftest import PROJECT_ROOT


def test_trae_codex_and_claude_discover_the_same_canonical_skill():
    workspace = PROJECT_ROOT.parents[2]
    discovery_paths = {
        "trae": workspace / ".trae" / "skills" / "macro-data",
        "codex": workspace / ".agents" / "skills" / "macro-data",
        "claude-code": workspace / ".claude" / "skills" / "macro-data",
    }

    assert {agent: path.resolve() for agent, path in discovery_paths.items()} == {
        "trae": PROJECT_ROOT,
        "codex": PROJECT_ROOT,
        "claude-code": PROJECT_ROOT,
    }
    assert all((path / "SKILL.md").is_file() for path in discovery_paths.values())
    assert all(
        (path / "scripts" / "run_datapro_first.py").is_file()
        for path in discovery_paths.values()
    )
