import os
from dataclasses import dataclass, field


def _default_cors_origins() -> list[str]:
    configured_origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
        ).split(",")
        if origin.strip()
    ]
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    if project_id:
        configured_origins.extend(
            [
                f"https://{project_id}.web.app",
                f"https://{project_id}.firebaseapp.com",
            ]
        )
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(configured_origins))


def _csv_env(name: str) -> list[str]:
    return [value.strip().lower() for value in os.getenv(name, "").split(",") if value.strip()]


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "Wildfire Ops Copilot"
    app_version: str = "0.1.0"
    cors_origins: list[str] = field(default_factory=_default_cors_origins)
    api_auth_token: str = field(default_factory=lambda: os.getenv("API_AUTH_TOKEN", "").strip())
    firebase_project_id: str = field(
        default_factory=lambda: os.getenv("FIREBASE_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", "")).strip()
    )
    auth_allowed_emails: list[str] = field(default_factory=lambda: _csv_env("AUTH_ALLOWED_EMAILS"))
    auth_admin_emails: list[str] = field(default_factory=lambda: _csv_env("AUTH_ADMIN_EMAILS"))
    auth_require_verified_email: bool = field(default_factory=lambda: _bool_env("AUTH_REQUIRE_VERIFIED_EMAIL", True))
    max_request_body_bytes: int = 64 * 1024
    demo_region_id: str = "live_australia"
    demo_region_name: str = "Australia Live Hotspot AOI"


settings = Settings()
