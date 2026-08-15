from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select

from app.authoring.models import PlatformRole, SessionUser
from app.config import Settings, get_settings
from app.persistence.database import SessionLocal
from app.persistence.models import (
    ConnectorRecord,
    PlatformSessionRecord,
    PlatformUserRecord,
    TenantRecord,
    UserRoleRecord,
)
from app.specifications.models import CapabilityState

DEVELOPMENT_IDENTITIES: dict[str, tuple[str, str, set[PlatformRole]]] = {
    "author": ("TENANT_DEMO", "Development Author", {PlatformRole.AUTHOR}),
    "reviewer": ("TENANT_DEMO", "Development Reviewer", {PlatformRole.REVIEWER}),
    "approver": ("TENANT_DEMO", "Development Approver", {PlatformRole.APPROVER}),
    "submitter": ("TENANT_DEMO", "Development Submitter", {PlatformRole.SUBMITTER}),
    "auditor": ("TENANT_DEMO", "Development Auditor", {PlatformRole.AUDITOR}),
    "admin": (
        "TENANT_DEMO",
        "Development Administrator",
        {PlatformRole.PROFILE_ADMIN, PlatformRole.SECURITY_ADMIN},
    ),
    "other-author": ("TENANT_OTHER", "Other Tenant Author", {PlatformRole.AUTHOR}),
}


def _hmac(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def _secret(settings: Settings) -> str:
    if settings.session_hmac_secret is None:
        raise RuntimeError("Session security is not configured")
    return settings.session_hmac_secret.get_secret_value()


def seed_platform_foundation(settings: Settings) -> None:
    if settings.auth_mode != "development":
        return
    with SessionLocal() as session:
        for tenant_id, tenant_name in (
            ("TENANT_DEMO", "Development Tenant"),
            ("TENANT_OTHER", "Isolation Test Tenant"),
        ):
            if session.get(TenantRecord, tenant_id) is None:
                session.add(
                    TenantRecord(
                        id=tenant_id,
                        name=tenant_name,
                        retention_days=settings.data_retention_days,
                    )
                )
        session.flush()
        for identity, (tenant_id, display_name, roles) in DEVELOPMENT_IDENTITIES.items():
            user_id = f"DEV-{identity.upper()}"
            if session.get(PlatformUserRecord, user_id) is None:
                session.add(
                    PlatformUserRecord(
                        id=user_id,
                        tenant_id=tenant_id,
                        subject=f"development:{identity}",
                        display_name=display_name,
                    )
                )
            existing_roles = set(
                session.scalars(
                    select(UserRoleRecord.role).where(UserRoleRecord.user_id == user_id)
                )
            )
            for role in roles:
                if role.value not in existing_roles:
                    session.add(UserRoleRecord(id=str(uuid4()), user_id=user_id, role=role.value))
        if session.get(ConnectorRecord, "DOWNLOAD-ONLY") is None:
            session.add(
                ConnectorRecord(
                    id="DOWNLOAD-ONLY",
                    tenant_id="TENANT_DEMO",
                    name="Secure download only",
                    connector_type="DOWNLOAD_ONLY",
                    environment="DOWNLOAD",
                    capability=CapabilityState.UAT_READY.value,
                    destination_alias="LOCAL_AUTHORISED_DOWNLOAD",
                    safe_configuration={},
                )
            )
        if settings.mock_uat_connector_enabled and session.get(ConnectorRecord, "MOCK-UAT") is None:
            session.add(
                ConnectorRecord(
                    id="MOCK-UAT",
                    tenant_id="TENANT_DEMO",
                    name="Explicit development mock UAT",
                    connector_type="MOCK_UAT",
                    environment="UAT",
                    capability=CapabilityState.UAT_READY.value,
                    destination_alias="MOCK_ALLOWLISTED_UAT",
                    safe_configuration={"testOnly": True},
                )
            )
        session.commit()


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    expires_at: datetime
    user: SessionUser


class SessionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def development_login(self, identity: str) -> IssuedSession:
        if self.settings.auth_mode != "development":
            raise HTTPException(status_code=404, detail="Development login is disabled")
        if identity not in DEVELOPMENT_IDENTITIES:
            raise HTTPException(status_code=401, detail="Unknown development identity")
        user_id = f"DEV-{identity.upper()}"
        token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.session_ttl_seconds)
        with SessionLocal() as session:
            user = session.get(PlatformUserRecord, user_id)
            if user is None or not user.active:
                raise HTTPException(status_code=401, detail="Account is disabled")
            roles = {
                PlatformRole(value)
                for value in session.scalars(
                    select(UserRoleRecord.role).where(UserRoleRecord.user_id == user_id)
                )
            }
            session.add(
                PlatformSessionRecord(
                    id=_hmac(_secret(self.settings), token),
                    user_id=user_id,
                    csrf_hash=_hmac(_secret(self.settings), csrf_token),
                    expires_at=expires_at,
                )
            )
            session.commit()
            return IssuedSession(
                token=token,
                csrf_token=csrf_token,
                expires_at=expires_at,
                user=SessionUser(
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    display_name=user.display_name,
                    roles=roles,
                ),
            )

    def authenticate(self, token: str | None) -> tuple[SessionUser, datetime] | None:
        if not token or self.settings.auth_mode == "disabled":
            return None
        session_id = _hmac(_secret(self.settings), token)
        with SessionLocal() as session:
            record = session.get(PlatformSessionRecord, session_id)
            if record is None:
                return None
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                session.delete(record)
                session.commit()
                return None
            user = session.get(PlatformUserRecord, record.user_id)
            if user is None or not user.active:
                return None
            roles = {
                PlatformRole(value)
                for value in session.scalars(
                    select(UserRoleRecord.role).where(UserRoleRecord.user_id == user.id)
                )
            }
            return (
                SessionUser(
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    display_name=user.display_name,
                    roles=roles,
                ),
                expires_at,
            )

    def verify_csrf(self, token: str, csrf_token: str | None) -> bool:
        if not csrf_token:
            return False
        session_id = _hmac(_secret(self.settings), token)
        with SessionLocal() as session:
            record = session.get(PlatformSessionRecord, session_id)
            return bool(
                record
                and hmac.compare_digest(record.csrf_hash, _hmac(_secret(self.settings), csrf_token))
            )

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with SessionLocal() as session:
            session.execute(
                delete(PlatformSessionRecord).where(
                    PlatformSessionRecord.id == _hmac(_secret(self.settings), token)
                )
            )
            session.commit()


def get_session_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionService:
    return SessionService(settings)


def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionUser:
    authenticated = SessionService(settings).authenticate(
        request.cookies.get(settings.session_cookie_name)
    )
    if authenticated is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return authenticated[0]


def get_optional_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionUser | None:
    if settings.session_hmac_secret is None:
        return None
    authenticated = SessionService(settings).authenticate(
        request.cookies.get(settings.session_cookie_name)
    )
    return authenticated[0] if authenticated else None


def require_roles(*allowed: PlatformRole):  # type: ignore[no-untyped-def]
    def dependency(
        user: Annotated[SessionUser, Depends(get_current_user)],
    ) -> SessionUser:
        if not user.roles.intersection(allowed):
            raise HTTPException(status_code=403, detail="Role is not authorised")
        return user

    return dependency


def require_csrf(
    request: Request,
    user: Annotated[SessionUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionUser:
    raw_token = request.cookies.get(settings.session_cookie_name)
    csrf_token = request.headers.get(settings.csrf_header_name)
    if raw_token is None or not SessionService(settings).verify_csrf(raw_token, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    return user
