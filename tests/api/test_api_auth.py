import importlib

import pytest
from fastapi.testclient import TestClient

import app.config.settings as settings_module
import app.services.api_auth as api_auth_module
from app.main import app


def _reload_auth_modules() -> None:
    importlib.reload(settings_module)
    importlib.reload(api_auth_module)


@pytest.fixture(autouse=True)
def reset_api_auth_settings(monkeypatch):
    yield
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    _reload_auth_modules()


def reload_auth_settings(monkeypatch, token: str) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", token)
    _reload_auth_modules()


def test_api_routes_allow_requests_when_auth_token_is_not_configured() -> None:
    client = TestClient(app)

    response = client.get("/api/hotspots/overview")

    assert response.status_code == 200


def test_api_routes_require_configured_auth_token(monkeypatch) -> None:
    reload_auth_settings(monkeypatch, "secret-token")
    client = TestClient(app)

    response = client.get("/api/hotspots/overview")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API credentials"


def test_api_routes_accept_x_api_key(monkeypatch) -> None:
    reload_auth_settings(monkeypatch, "secret-token")
    client = TestClient(app)

    response = client.get("/api/hotspots/overview", headers={"X-API-Key": "secret-token"})

    assert response.status_code == 200


def test_api_routes_accept_bearer_token(monkeypatch) -> None:
    reload_auth_settings(monkeypatch, "secret-token")
    client = TestClient(app)

    response = client.get("/api/hotspots/overview", headers={"Authorization": "Bearer secret-token"})

    assert response.status_code == 200


def test_health_check_does_not_require_api_token(monkeypatch) -> None:
    reload_auth_settings(monkeypatch, "secret-token")
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
