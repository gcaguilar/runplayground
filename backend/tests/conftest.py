"""Test environment must be configured before importing the application."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="run-dashboard-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["DATA_DIR"] = str(_TMP / "data")
os.environ["SYNC_INTERVAL_HOURS"] = "0"
os.environ["SYNC_ON_STARTUP"] = "false"
os.environ["AUTH_MODE"] = "none"
os.environ["GARMIN_PERSONAL_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, create_all, get_engine  # noqa: E402
from app.main import app  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def client():
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    create_all()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def sample_fit() -> bytes:
    return (FIXTURES / "sample.fit").read_bytes()


@pytest.fixture()
def sample_tcx() -> bytes:
    return (FIXTURES / "sample.tcx").read_bytes()


@pytest.fixture()
def sample_gpx() -> bytes:
    return (FIXTURES / "sample.gpx").read_bytes()
