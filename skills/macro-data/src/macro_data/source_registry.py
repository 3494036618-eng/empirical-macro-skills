"""Explicit registry of enabled macro-data providers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDescriptor:
    code: str
    kind: str
    connector_name: str
    priority: int
    enabled: bool = True


class SourceRegistry:
    def __init__(self, descriptors: list[SourceDescriptor]) -> None:
        codes = [descriptor.code for descriptor in descriptors]
        if len(codes) != len(set(codes)):
            raise ValueError("source codes must be unique")
        self._descriptors = {descriptor.code: descriptor for descriptor in descriptors}

    @classmethod
    def default(cls) -> SourceRegistry:
        return cls(
            [
                SourceDescriptor(
                    code="datapro",
                    kind="aggregator",
                    connector_name="DataProConnector",
                    priority=0,
                ),
                SourceDescriptor(
                    code="world_bank",
                    kind="official",
                    connector_name="WorldBankConnector",
                    priority=10,
                ),
            ]
        )

    def get(self, code: str) -> SourceDescriptor | None:
        return self._descriptors.get(code)

    def enabled_codes(self) -> list[str]:
        return [
            descriptor.code
            for descriptor in sorted(
                self._descriptors.values(),
                key=lambda item: (item.priority, item.code),
            )
            if descriptor.enabled
        ]

    def primary(self) -> SourceDescriptor:
        enabled = [descriptor for descriptor in self._descriptors.values() if descriptor.enabled]
        if not enabled:
            raise RuntimeError("no enabled source")
        return min(enabled, key=lambda item: (item.priority, item.code))
