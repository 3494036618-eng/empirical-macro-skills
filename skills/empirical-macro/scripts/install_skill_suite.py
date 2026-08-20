#!/usr/bin/env python3
"""Install or uninstall the portable six-Skill suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from empirical_macro.installer import (
    HostName,
    InstallTarget,
    install_suite,
    uninstall_suite,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    install = subparsers.add_parser("install")
    install.add_argument("--source-root", type=Path, required=True)
    uninstall = subparsers.add_parser("uninstall")
    uninstall.add_argument("--manifest", type=Path, required=True)
    for command in (install, uninstall):
        command.add_argument(
            "--host",
            choices=("generic", "trae", "codex", "claude-code"),
            required=True,
        )
        command.add_argument("--target-root", type=Path, required=True)
        command.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    target = InstallTarget(
        host=cast(HostName, args.host),
        root=args.target_root,
    )
    if args.operation == "install":
        report = install_suite(
            source_root=args.source_root,
            target=target,
            dry_run=args.dry_run,
        )
    else:
        report = uninstall_suite(
            target=target,
            manifest_path=args.manifest,
            dry_run=args.dry_run,
        )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
