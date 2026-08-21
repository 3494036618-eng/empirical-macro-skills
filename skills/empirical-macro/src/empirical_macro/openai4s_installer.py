"""Suite transaction over OpenAI4S's public SkillVersionService."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

INSTALL_ORDER = (
    "research-design",
    "macro-data",
    "time-series-dynamics",
    "robustness-audit",
    "research-synthesis",
    "empirical-macro",
)


class OpenAI4SSuiteInstallError(RuntimeError):
    def __init__(self, message: str, report: dict[str, object]) -> None:
        super().__init__(message)
        self.report = report


class SkillVersionService(Protocol):
    def status(self, name: str, **kwargs: object) -> dict[str, object]: ...

    def install_directory(
        self,
        name: str,
        root: Path,
        **kwargs: object,
    ) -> dict[str, Any]: ...

    def rollback(
        self,
        name: str,
        version_id: str,
        **kwargs: object,
    ) -> object: ...

    def delete(self, name: str, **kwargs: object) -> object: ...


class SkillLoader(Protocol):
    def discover(self) -> dict[str, Any]: ...


def _scope_args(scope: str, project_id: str | None) -> dict[str, object]:
    if scope not in {"personal", "project"}:
        raise ValueError("scope must be personal or project")
    if scope == "project" and not project_id:
        raise ValueError("project scope requires project_id")
    if scope == "personal" and project_id:
        raise ValueError("personal scope cannot have project_id")
    return {"scope": scope, "project_id": project_id}


def _restore(
    service: SkillVersionService,
    changed: list[str],
    before: dict[str, str | None],
    scope_args: dict[str, object],
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for name in reversed(changed):
        try:
            version = before[name]
            if version is None:
                service.delete(name, **scope_args)
            else:
                service.rollback(name, version, **scope_args)
        except Exception as error:  # noqa: BLE001 - every failed restore is reported
            failures.append(
                {
                    "skill": name,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    return failures


def install_openai4s_suite(
    *,
    source_root: Path,
    service: SkillVersionService,
    loader_factory: Callable[[], SkillLoader],
    scope: str = "personal",
    project_id: str | None = None,
) -> dict[str, object]:
    scope_args = _scope_args(scope, project_id)
    before: dict[str, str | None] = {}
    for name in INSTALL_ORDER:
        status = service.status(name, **scope_args)
        before[name] = (
            str(status["active_version_id"])
            if status.get("active") and status.get("active_version_id")
            else None
        )

    changed: list[str] = []
    installed: list[dict[str, Any]] = []
    try:
        for name in INSTALL_ORDER:
            root = source_root / name
            if not (root / "SKILL.md").is_file():
                raise FileNotFoundError(f"missing Skill package: {name}")
            installed.append(
                service.install_directory(
                    name,
                    root,
                    **scope_args,
                )
            )
            changed.append(name)

        discovered = loader_factory().discover()
        missing = [name for name in INSTALL_ORDER if name not in discovered]
        if missing:
            raise RuntimeError("installed Skills not discoverable: " + ", ".join(missing))
        failed_gates = [
            name
            for name in INSTALL_ORDER
            if discovered[name].sidecar_gate().get("ok") is not True
        ]
        if failed_gates:
            raise RuntimeError("sidecar compile gate failed: " + ", ".join(failed_gates))
    except Exception as error:
        restore_failures = _restore(service, changed, before, scope_args)
        report: dict[str, object] = {
            "valid": False,
            "installed_skills": changed,
            "failed_skill": INSTALL_ORDER[len(changed)] if len(changed) < 6 else None,
            "restored": not restore_failures,
            "restore_failures": restore_failures,
        }
        raise OpenAI4SSuiteInstallError(str(error), report) from error

    return {
        "valid": True,
        "scope": scope,
        "installed_skills": list(INSTALL_ORDER),
        "sidecar_gates_passed": len(INSTALL_ORDER),
        "versions": {
            str(item["name"]): str(item["version_id"])
            for item in installed
        },
    }
