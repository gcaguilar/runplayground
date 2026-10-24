"""Optional password auth with a signed, HttpOnly session cookie.

Default mode is ``none``: the container is expected to bind to localhost or sit
behind Tailscale/a reverse proxy. Password mode is opt-in via ``AUTH_MODE``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status

from app.config import Settings, get_settings

COOKIE_NAME = "run_session"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _signature(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def create_session(secret: str, days: int) -> str:
    payload = _b64encode(
        json.dumps({"exp": int(time.time()) + days * 86400}, separators=(",", ":")).encode()
    )
    return f"{payload}.{_signature(payload, secret)}"


def verify_session(value: str | None, secret: str) -> bool:
    if not value or "." not in value:
        return False
    payload, signature = value.rsplit(".", 1)
    if not hmac.compare_digest(signature, _signature(payload, secret)):
        return False
    try:
        data = json.loads(_b64decode(payload))
        return int(data["exp"]) > int(time.time())
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False


def is_authenticated(session_cookie: str | None, settings: Settings) -> bool:
    if settings.auth_mode == "none":
        return True
    if not settings.secret_key:
        return False
    return verify_session(session_cookie, settings.secret_key.get_secret_value())


def require_auth(
    session_cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> None:
    if not is_authenticated(session_cookie, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


def check_password(candidate: str, settings: Settings) -> bool:
    if not settings.app_password:
        return False
    expected = settings.app_password.get_secret_value()
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))
