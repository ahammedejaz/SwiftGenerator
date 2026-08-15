"""Service authentication for the automation API.

Interactive user authentication (session cookie, CSRF, RBAC) and automation
authentication are deliberately separate concerns. An automation framework should not have
to drive a login screen, and an interactive user should not have to hold a long-lived key.

Behaviour:

* Keys come from the ``AUTOMATION_API_KEYS`` environment variable only. None is ever
  committed to source, and the value is never echoed back in a response or a log line.
* In development, when no keys are configured, ``/api/v1`` is open. That is what makes a
  fresh clone usable with no setup.
* Outside development the API is closed unless keys are configured, and requests are
  rejected with a message that says how to configure one — never with a hint about what a
  valid key looks like.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from app.config import Settings, get_settings

API_KEY_HEADER = "X-API-Key"


class AutomationPrincipal:
    """Who is calling the automation API, for audit and for the source column."""

    def __init__(self, name: str, authenticated: bool) -> None:
        self.name = name
        self.authenticated = authenticated

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AutomationPrincipal(name={self.name!r}, authenticated={self.authenticated})"


def _configured_keys(settings: Settings) -> list[str]:
    raw = settings.automation_api_keys.get_secret_value() if settings.automation_api_keys else ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def automation_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
) -> AutomationPrincipal:
    keys = _configured_keys(settings)
    open_in_development = settings.app_env in {"development", "test"}

    if not keys:
        if open_in_development:
            return AutomationPrincipal(name="local-development", authenticated=False)
        raise HTTPException(
            status_code=503,
            detail=(
                "The automation API is not configured. Set AUTOMATION_API_KEYS on the server "
                "to enable it."
            ),
        )
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail=f"An {API_KEY_HEADER} header is required for the automation API.",
        )
    # compare_digest against every configured key so timing does not reveal which matched
    if not any(hmac.compare_digest(api_key, candidate) for candidate in keys):
        raise HTTPException(status_code=401, detail="The supplied API key was not recognised.")
    # The key itself is never stored or returned; only its position is used as a label.
    index = next(
        index
        for index, candidate in enumerate(keys, start=1)
        if hmac.compare_digest(api_key, candidate)
    )
    request.state.automation_principal = f"service-key-{index}"
    return AutomationPrincipal(name=f"service-key-{index}", authenticated=True)


AutomationCaller = Annotated[AutomationPrincipal, Depends(automation_principal)]
