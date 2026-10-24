"""Authentication endpoints (public)."""

from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth import COOKIE_NAME, check_password, create_session
from app.config import Settings, get_settings
from app.schemas import AuthStatus, LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])

_attempts: dict[str, deque[float]] = defaultdict(deque)
_WINDOW_SECONDS = 300
_MAX_ATTEMPTS = 10


def _throttled(ip: str) -> bool:
    now = monotonic()
    attempts = _attempts[ip]
    while attempts and now - attempts[0] > _WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= _MAX_ATTEMPTS


@router.get("/status", response_model=AuthStatus)
def auth_status(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthStatus:
    from app.auth import is_authenticated

    cookie = request.cookies.get(COOKIE_NAME)
    return AuthStatus(
        auth_mode=settings.auth_mode,
        authenticated=is_authenticated(cookie, settings),
    )


@router.post("/login", response_model=AuthStatus)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthStatus:
    if settings.auth_mode == "none":
        return AuthStatus(auth_mode="none", authenticated=True)

    ip = request.client.host if request.client else "unknown"
    if _throttled(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts; try again in a few minutes",
        )

    if not check_password(payload.password, settings):
        _attempts[ip].append(monotonic())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )

    _attempts.pop(ip, None)
    assert settings.secret_key is not None
    token = create_session(settings.secret_key.get_secret_value(), settings.session_days)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return AuthStatus(auth_mode="password", authenticated=True)


@router.post("/logout", response_model=AuthStatus)
def logout(response: Response, settings: Settings = Depends(get_settings)) -> AuthStatus:
    response.delete_cookie(COOKIE_NAME, path="/")
    return AuthStatus(auth_mode=settings.auth_mode, authenticated=settings.auth_mode == "none")
