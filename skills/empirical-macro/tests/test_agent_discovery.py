from __future__ import annotations

import json
import subprocess
import sys

from tests.helpers import ROOT, read_skill_frontmatter


def test_skill_frontmatter_and_description() -> None:
    """Break caught: host agents cannot discover the total routing Skill."""
    document = read_skill_frontmatter(ROOT / "SKILL.md")
    assert document["name"] == "empirical-macro"
    assert len(document["description"]) <= 200
    assert "Invoke" in document["description"]
    assert set(document) == {"name", "description"}


def test_skill_references_and_interface_metadata_are_complete() -> None:
    """Break caught: discovery succeeds but runtime instructions are missing."""
    for path in (
        ROOT / "agents" / "openai.yaml",
        ROOT / "references" / "routing-policy.md",
        ROOT / "references" / "supported-scope.md",
        ROOT / "references" / "artifact-handoffs.md",
        ROOT / "THIRD_PARTY_NOTICES.md",
    ):
        assert path.is_file(), path
    metadata = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert 'display_name: "宏观经济实证动态研究"' in metadata
    assert "当前版本不能执行该方法" in metadata


def test_quick_validator_reports_valid_json() -> None:
    """Break caught: a structurally incomplete Skill is installable."""
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "quick_validate.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["valid"] is True
    assert report["issue_codes"] == []
