"""Shared fixtures for API route tests."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Point db.DB_PATH at a tmp file and initialize schema."""
    from valor.server import db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield


@pytest.fixture
def client(tmp_db):
    """TestClient with initialized tmp SQLite."""
    from valor.server.main import app

    return TestClient(app)
