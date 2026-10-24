"""Application configuration.

All configuration comes from environment variables (or a local ``.env`` file).
Nothing secret is ever persisted in SQLite.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- identity ---------------------------------------------------------
    app_name: str = "Run"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # --- storage ----------------------------------------------------------
    data_dir: Path = Path("data")
    database_url: str | None = None
    max_upload_mb: int = 50

    # --- web --------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    static_dir: Path | None = None

    # --- Garmin Personal API ---------------------------------------------
    garmin_personal_api_key: SecretStr | None = None
    garmin_api_base_url: str = "https://personal.connectapi.garmin.com"
    garmin_timeout_seconds: float = 30.0
    sync_download_fit: bool = True
    sync_interval_hours: int = 12
    sync_on_startup: bool = False
    sync_incremental_max_pages: int = 3
    sync_backfill_max_pages: int = 100
    sync_request_delay_seconds: float = 0.2

    # --- auth -------------------------------------------------------------
    auth_mode: Literal["none", "password"] = "none"
    app_password: SecretStr | None = None
    secret_key: SecretStr | None = None
    session_days: int = 30

    # --- presentation -----------------------------------------------------
    # Locale and units are stored in the browser (localStorage).

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'run.db').as_posix()}"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def garmin_configured(self) -> bool:
        if not self.garmin_personal_api_key:
            return False
        return bool(self.garmin_personal_api_key.get_secret_value().strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @model_validator(mode="after")
    def _validate_auth(self) -> Settings:
        if self.auth_mode == "password":
            if not self.app_password or not self.app_password.get_secret_value():
                raise ValueError("AUTH_MODE=password requires APP_PASSWORD to be set")
            if not self.secret_key or len(self.secret_key.get_secret_value()) < 16:
                raise ValueError(
                    "AUTH_MODE=password requires SECRET_KEY with at least 16 characters"
                )
        return self

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


def configure_logging(level: str | None = None) -> None:
    logging.basicConfig(
        level=(level or get_settings().log_level).upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
