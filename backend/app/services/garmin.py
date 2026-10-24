"""Garmin Connect Personal API client.

Only the official, self-serve Personal API is used here. It is read-only and
authorised with a personal API key that the user creates in Garmin Connect.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
REFRESH_WINDOW_SECONDS = 10 * 60
USER_AGENT = "run-dashboard/0.1.0 (+self-hosted; Garmin Personal API)"


class GarminError(RuntimeError):
    pass


class GarminAuthError(GarminError):
    pass


class GarminApiError(GarminError):
    def __init__(self, status_code: int, message: str, url: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url


@dataclass(frozen=True)
class BearerToken:
    access_token: str
    expires_at: float

    @property
    def expires_in(self) -> float:
        return self.expires_at - time.time()


def _jwt_expiration(token: str) -> float:
    try:
        payload = token.split(".")[1]
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        claim = json.loads(decoded)
        return float(claim["exp"])
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise GarminAuthError("Garmin returned a token without a valid exp claim") from exc


class GarminAuth:
    """Exchange the personal API key for a 24 h bearer token and cache it."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._lock = threading.Lock()
        self._token: BearerToken | None = None

    @property
    def configured(self) -> bool:
        return self.settings.garmin_configured

    def _key(self) -> str:
        if not self.settings.garmin_personal_api_key:
            raise GarminAuthError(
                "GARMIN_PERSONAL_API_KEY is not configured. Create a key in Garmin Connect "
                "and add it to .env."
            )
        key = self.settings.garmin_personal_api_key.get_secret_value().strip()
        if not key:
            raise GarminAuthError("GARMIN_PERSONAL_API_KEY is empty")
        return key

    def get_token(self, force: bool = False) -> BearerToken:
        with self._lock:
            if (
                not force
                and self._token is not None
                and self._token.expires_in > REFRESH_WINDOW_SECONDS
            ):
                return self._token

            url = f"{self.settings.garmin_api_base_url.rstrip('/')}{TOKEN_PATH}"
            try:
                response = httpx.post(
                    url,
                    headers={
                        "Accept": "*/*",
                        "Authorization": f"ApiKey {self._key()}",
                        "User-Agent": USER_AGENT,
                    },
                    timeout=self.settings.garmin_timeout_seconds,
                )
            except httpx.HTTPError as exc:
                raise GarminAuthError(f"Could not reach Garmin: {exc}") from exc

            if response.status_code >= 400:
                detail = _error_detail(response)
                raise GarminAuthError(
                    f"Garmin rejected the personal API key ({response.status_code}): {detail}"
                )

            token_text = response.text.strip()
            if not token_text:
                raise GarminAuthError("Garmin returned an empty access token")
            self._token = BearerToken(token_text, _jwt_expiration(token_text))
            logger.info(
                "Obtained Garmin bearer token, expires in %.1f hours",
                self._token.expires_in / 3600,
            )
            return self._token

    def invalidate(self) -> None:
        with self._lock:
            self._token = None

    def peek(self) -> BearerToken | None:
        """Return the cached token without touching the network."""
        with self._lock:
            return self._token


class GarminClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.auth = GarminAuth(self.settings)
        self.base_url = self.settings.garmin_api_base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.settings.garmin_timeout_seconds, read=120.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GarminClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        accept: str | None = None,
        max_retries: int = 3,
    ) -> httpx.Response:
        refreshed = False
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            token = self.auth.get_token()
            headers = {"Authorization": f"Bearer {token.access_token}"}
            if accept:
                headers["Accept"] = accept
            try:
                response = self._client.request(method, path, params=params, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= max_retries:
                    break
                time.sleep(min(2**attempt, 8))
                continue

            if response.status_code == 401 and not refreshed:
                refreshed = True
                self.auth.invalidate()
                continue

            if (
                response.status_code == 429 or response.status_code >= 500
            ) and attempt < max_retries:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                logger.warning(
                    "Garmin %s %s returned %s; retrying in %.1fs",
                    method,
                    path,
                    response.status_code,
                    delay,
                )
                time.sleep(min(delay, 30))
                continue

            if response.status_code >= 400:
                raise GarminApiError(
                    response.status_code,
                    f"Garmin API error {response.status_code}: {_error_detail(response)}",
                    url=str(response.url),
                )
            return response

        raise GarminError(f"Could not reach Garmin after retries: {last_error}")

    def get_activities(self, start: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            "/activitylist-service/activities/search/activities",
            params={"start": start, "limit": min(limit, 60)},
        )
        data = response.json()
        return data if isinstance(data, list) else []

    def get_activity(self, activity_id: int | str) -> dict[str, Any]:
        response = self._request("GET", f"/activity-service/activity/{activity_id}")
        data = response.json()
        return data if isinstance(data, dict) else {}

    def download_activity_file(self, activity_id: int | str) -> bytes:
        response = self._request(
            "GET",
            f"/download-service/files/activity/{activity_id}",
            accept="application/octet-stream",
        )
        return response.content

    def get_profile(self) -> dict[str, Any]:
        response = self._request("GET", "/userprofile-service/userprofile/settings")
        data = response.json()
        return data if isinstance(data, dict) else {}

    def token_status(self) -> dict[str, Any]:
        token = self.auth.peek()
        return {
            "configured": self.settings.garmin_configured,
            "cached": token is not None,
            "expires_at": token.expires_at if token else None,
            "expires_in_seconds": int(token.expires_in) if token else None,
        }


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            for key in ("message", "error", "detail", "error_description"):
                if payload.get(key):
                    return str(payload[key])[:500]
        return str(payload)[:500]
    except ValueError:
        return response.text.strip()[:500] or response.reason_phrase
