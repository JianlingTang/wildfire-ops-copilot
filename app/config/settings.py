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


@dataclass(frozen=True)
class Settings:
    app_name: str = "Wildfire Ops Copilot"
    app_version: str = "0.1.0"
    cors_origins: list[str] = field(default_factory=_default_cors_origins)
    demo_region_id: str = "live_australia"
    demo_region_name: str = "Australia Live Hotspot AOI"


settings = Settings()
