#!/usr/bin/env python3
"""Install the same six Skills into generic hosts or OpenAI4S."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER_SRC = ROOT / "skills" / "empirical-macro" / "src"
if str(ROUTER_SRC) not in sys.path:
    sys.path.insert(0, str(ROUTER_SRC))

HOSTS = ("generic", "trae", "codex", "claude-code", "openai4s")
MINIMUM_PYTHON = (3, 12)
PYTHON_VERSION_ERROR = (
    "Python 3.12 or newer is required; run this installer with uv"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("install", "uninstall"))
    parser.add_argument("--host", choices=HOSTS, required=True)
    parser.add_argument("--target-root", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--scope", choices=("personal", "project"), default="personal")
    parser.add_argument("--project-id")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _openai4s_install(args: argparse.Namespace) -> dict[str, object]:
    if args.operation != "install":
        raise ValueError(
            "OpenAI4S uninstall uses its Skill version UI or SkillVersionService"
        )
    if args.dry_run:
        return {
            "valid": True,
            "dry_run": True,
            "host": "openai4s",
            "scope": args.scope,
            "skills": sorted(path.name for path in (ROOT / "skills").iterdir()),
        }
    try:
        from openai4s.skills_loader import SkillLoader, SkillVersionService
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "OpenAI4S is not installed in this Python environment"
        ) from error
    from empirical_macro.openai4s_installer import install_openai4s_suite

    return install_openai4s_suite(
        source_root=ROOT / "skills",
        service=SkillVersionService(),
        loader_factory=lambda: SkillLoader(project_id=args.project_id),
        scope=args.scope,
        project_id=args.project_id,
    )


def _directory_host(args: argparse.Namespace) -> dict[str, object]:
    if args.target_root is None:
        raise ValueError("--target-root is required for directory-based hosts")
    from empirical_macro.installer import (
        InstallTarget,
        install_suite,
        uninstall_suite,
    )

    target = InstallTarget(host=args.host, root=args.target_root)
    if args.operation == "install":
        return install_suite(
            source_root=ROOT / "skills",
            target=target,
            dry_run=args.dry_run,
        )
    if args.manifest is None:
        raise ValueError("--manifest is required for uninstall")
    return uninstall_suite(
        target=target,
        manifest_path=args.manifest,
        dry_run=args.dry_run,
    )


def main() -> int:
    if sys.version_info < MINIMUM_PYTHON:
        print(json.dumps({"valid": False, "error": PYTHON_VERSION_ERROR}))
        return 1
    args = _parser().parse_args()
    try:
        report = (
            _openai4s_install(args)
            if args.host == "openai4s"
            else _directory_host(args)
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(json.dumps({"valid": False, "error": str(error)}))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
