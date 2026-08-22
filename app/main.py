from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import actions, agent_events, alerts, chat, hotspots, monitor_tasks, reports, runs
from app.config.settings import settings
from app.services.api_auth import verify_api_request
from app.services.monitoring_tasks import start_monitor_loop

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def reject_oversized_requests(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > settings.max_request_body_bytes:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": "Request body too large"},
        )
    return await call_next(request)

api_dependencies = [Depends(verify_api_request)]

app.include_router(runs.router, prefix="/api", dependencies=api_dependencies)
app.include_router(agent_events.router, prefix="/api", dependencies=api_dependencies)
app.include_router(chat.router, prefix="/api", dependencies=api_dependencies)
app.include_router(hotspots.router, prefix="/api", dependencies=api_dependencies)
app.include_router(alerts.router, prefix="/api", dependencies=api_dependencies)
app.include_router(actions.router, prefix="/api", dependencies=api_dependencies)
app.include_router(reports.router, prefix="/api", dependencies=api_dependencies)
app.include_router(monitor_tasks.router, prefix="/api", dependencies=api_dependencies)


@app.on_event("startup")
def startup() -> None:
    start_monitor_loop()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name}
