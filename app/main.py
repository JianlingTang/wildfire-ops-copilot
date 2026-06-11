from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import actions, agent_events, alerts, chat, hotspots, monitor_tasks, reports, runs
from app.config.settings import settings
from app.services.monitoring_tasks import start_monitor_loop

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router, prefix="/api")
app.include_router(agent_events.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(hotspots.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(actions.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(monitor_tasks.router, prefix="/api")


@app.on_event("startup")
def startup() -> None:
    start_monitor_loop()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name}
