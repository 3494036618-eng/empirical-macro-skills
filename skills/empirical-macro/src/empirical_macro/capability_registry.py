from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import cast, get_args

from empirical_macro.models import CapabilityDecision, MethodFamily

METHOD_NOT_IMPLEMENTED_MESSAGE = "当前版本不能执行该方法"
PACKAGE_CONFIG_ROOT = Path(__file__).resolve().parent / "configs"
SOURCE_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"
CONFIG_ROOT = (
    PACKAGE_CONFIG_ROOT if PACKAGE_CONFIG_ROOT.is_dir() else SOURCE_CONFIG_ROOT
)
REGISTRY_PATH = CONFIG_ROOT / "capability-registry.json"
METHOD_FAMILIES = frozenset(get_args(MethodFamily))


@lru_cache(maxsize=1)
def load_registry() -> dict[str, object]:
    document = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("capability registry must be an object")
    registry = cast(dict[str, object], document)
    if registry.get("schema_version") != "0.1.0-beta":
        raise ValueError("capability registry schema version mismatch")
    capabilities = registry.get("capabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != METHOD_FAMILIES:
        raise ValueError("capability registry coverage mismatch")
    return registry


def registry_version() -> str:
    value = load_registry().get("registry_version")
    if not isinstance(value, str) or not value:
        raise ValueError("capability registry version missing")
    return value


def resolve_capability(method_family: str) -> CapabilityDecision:
    if method_family not in METHOD_FAMILIES:
        raise ValueError(f"unknown method family: {method_family}")
    family = cast(MethodFamily, method_family)
    capabilities = cast(dict[str, object], load_registry()["capabilities"])
    entry = capabilities[family]
    if not isinstance(entry, dict):
        raise ValueError(f"invalid capability entry: {family}")
    executable = entry.get("executable")
    executor = entry.get("executor_skill")
    if not isinstance(executable, bool):
        raise ValueError(f"invalid executable flag: {family}")
    if executable:
        if executor != "time-series-dynamics":
            raise ValueError(f"invalid executor skill: {family}")
        return CapabilityDecision(family, True, str(executor), None, None)
    if executor is not None:
        raise ValueError(f"unsupported method has executor: {family}")
    return CapabilityDecision(
        family,
        False,
        None,
        "method_not_implemented",
        METHOD_NOT_IMPLEMENTED_MESSAGE,
    )
