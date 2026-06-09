from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import actions, alerts, chat, hotspots, reports, runs
from app.config.settings import settings

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(hotspots.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(actions.router, prefix="/api")
app.include_router(reports.router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name}
