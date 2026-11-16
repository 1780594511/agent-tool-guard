import pytest
from fastapi.testclient import TestClient

from toolguard.api import create_app
from toolguard.auth import login
from toolguard.db import Database
from toolguard.gateway import Gateway
from toolguard.seed import seed


@pytest.fixture
def db(tmp_path):
    store = Database(tmp_path / "test.sqlite3")
    seed(store)
    return store


@pytest.fixture
def tokens(db):
    return {
        name: login(db, name, "Demo-Only-2026!")["token"]
        for name in ("employee", "engineer", "hr", "approver", "admin")
    }


@pytest.fixture
def gateway(db):
    return Gateway(db)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "api.sqlite3")) as test_client:
        yield test_client


def sign_in(client, username="employee"):
    response = client.post("/api/auth/login", json={"username": username, "password": "Demo-Only-2026!"})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response
