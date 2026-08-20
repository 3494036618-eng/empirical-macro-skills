"""Provider-neutral connector contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ConnectorRequest:
    request_id: str
    query: str
    research_request: dict[str, Any] | None = None


@dataclass(frozen=True)
class ConnectorResponse:
    provider: str
    request_id: str
    raw: dict[str, Any]
    retrieved_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@runtime_checkable
class Connector(Protocol):
    code: str

    def retrieve(self, request: ConnectorRequest) -> ConnectorResponse:
        """Retrieve a sanitized provider response."""

    def parse_response(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Parse provider-native raw data into canonical candidates."""
