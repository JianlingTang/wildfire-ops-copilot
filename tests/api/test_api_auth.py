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
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("AUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("AUTH_ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("AUTH_REQUIRE_VERIFIED_EMAIL", raising=False)
    _reload_auth_modules()
    yield
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("AUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("AUTH_ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("AUTH_REQUIRE_VERIFIED_EMAIL", raising=False)
    _reload_auth_modules()


def reload_auth_settings(monkeypatch, *, allowed: str = "operator@example.com", admins: str = "") -> None:
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "wildfireops-test")
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", allowed)
    monkeypatch.setenv("AUTH_ADMIN_EMAILS", admins)
    _reload_auth_modules()


def test_api_routes_allow_requests_when_auth_token_is_not_configured() -> None:
    client = TestClient(app)

    response = client.get("/api/hotspots/overview")

    assert response.status_code == 200


def test_api_routes_require_configured_firebase_auth(monkeypatch) -> None:
    reload_auth_settings(monkeypatch)
    client = TestClient(app)

    response = client.get("/api/hotspots/overview")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API credentials"


def test_api_routes_accept_valid_firebase_bearer_token(monkeypatch) -> None:
    reload_auth_settings(monkeypatch)
    monkeypatch.setattr(
        api_auth_module.id_token,
        "verify_firebase_token",
        lambda *args, **kwargs: {"user_id": "user-1", "email": "operator@example.com", "email_verified": True},
    )
    client = TestClient(app)

    response = client.get("/api/hotspots/overview", headers={"Authorization": "Bearer firebase-id-token"})

    assert response.status_code == 200


def test_api_routes_reject_users_not_on_allowlist(monkeypatch) -> None:
    reload_auth_settings(monkeypatch)
    monkeypatch.setattr(
        api_auth_module.id_token,
        "verify_firebase_token",
        lambda *args, **kwargs: {"user_id": "user-2", "email": "outsider@example.com", "email_verified": True},
    )
    client = TestClient(app)

    response = client.get("/api/hotspots/overview", headers={"Authorization": "Bearer firebase-id-token"})

    assert response.status_code == 403


def test_api_routes_reject_unverified_email_by_default(monkeypatch) -> None:
    reload_auth_settings(monkeypatch)
    monkeypatch.setattr(
        api_auth_module.id_token,
        "verify_firebase_token",
        lambda *args, **kwargs: {"user_id": "user-3", "email": "operator@example.com", "email_verified": False},
    )
    client = TestClient(app)

    response = client.get("/api/hotspots/overview", headers={"Authorization": "Bearer firebase-id-token"})

    assert response.status_code == 401


def test_api_routes_reject_invalid_firebase_bearer_token(monkeypatch) -> None:
    reload_auth_settings(monkeypatch)

    def reject_token(*args, **kwargs):
        raise ValueError("invalid token")

    monkeypatch.setattr(api_auth_module.id_token, "verify_firebase_token", reject_token)
    client = TestClient(app)

    response = client.get("/api/hotspots/overview", headers={"Authorization": "Bearer invalid-token"})

    assert response.status_code == 401


def test_health_check_does_not_require_api_token(monkeypatch) -> None:
    reload_auth_settings(monkeypatch)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
