from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.authoring.models import PlatformRole


@dataclass(frozen=True)
class VerifiedIdentity:
    subject: str
    tenant_id: str
    display_name: str
    roles: set[PlatformRole]


class IdentityProviderAdapter(Protocol):
    """Boundary for an institution-approved OIDC or SAML implementation."""

    async def authenticate_callback(self, payload: str, state: str) -> VerifiedIdentity: ...

    async def disabled_subjects(self) -> set[str]: ...


class IdentityProviderNotConfigured(RuntimeError):
    """Safe health signal; no development identity is silently substituted."""
