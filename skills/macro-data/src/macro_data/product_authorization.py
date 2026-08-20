"""Interpret product-scoped DataPro use authorization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class UseAuthorization:
    authorization_id: str
    authorization_basis: str
    data_use_scope: str
    allowed_scopes: tuple[str, ...]
    public_payload_policy: str

    @classmethod
    def from_document(
        cls,
        document: dict[str, Any],
    ) -> UseAuthorization:
        return cls(
            authorization_id=str(document["authorization_id"]),
            authorization_basis=str(document["authorization_basis"]),
            data_use_scope=str(document["data_use_scope"]),
            allowed_scopes=tuple(str(value) for value in document["allowed_scopes"]),
            public_payload_policy=str(document["public_payload_policy"]),
        )

    @property
    def authorized(self) -> bool:
        return self.data_use_scope in self.allowed_scopes


def request_authorization(
    request: dict[str, Any],
) -> UseAuthorization | None:
    raw = request.get("product_authorization")
    if not isinstance(raw, dict):
        return None
    return UseAuthorization.from_document(raw)


def authorization_issues(
    request: dict[str, Any],
    candidate: dict[str, Any],
) -> set[str]:
    if candidate.get("provider") != "datapro":
        return set()
    authorization = request_authorization(request)
    if authorization is None:
        return {"product_authorization_missing"}
    if not authorization.authorized:
        return {"scope_not_authorized"}
    return set()


def use_authorization_document(
    request: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, str] | None:
    if candidate.get("provider") != "datapro":
        return None
    authorization = request_authorization(request)
    if authorization is None:
        return None
    return {
        "authorization_ref": authorization.authorization_id,
        "authorization_basis": authorization.authorization_basis,
        "scope": authorization.data_use_scope,
        "status": ("authorized" if authorization.authorized else "denied"),
    }
