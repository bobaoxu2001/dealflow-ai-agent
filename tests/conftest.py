"""Shared pytest fixtures.

Uses an isolated temporary SQLite database so the full stack (models, vector
search, agent graph, approval flow) runs with zero external infrastructure.
"""
from __future__ import annotations

import os
import tempfile

import pytest

# Configure an isolated DB BEFORE importing any app module (settings are cached
# at import time and the engine binds to DATABASE_URL immediately).
_TMP_DB = os.path.join(tempfile.gettempdir(), "dealflow_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["EMBEDDING_PROVIDER"] = "local"

from fastapi.testclient import TestClient  # noqa: E402

from app.db.init_db import init_db  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from scripts.seed_demo_data import seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _prepare_db():
    init_db()
    session = SessionLocal()
    try:
        seed(session)
        session.commit()
    finally:
        session.close()
    yield


@pytest.fixture()
def session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client():
    return TestClient(app)
