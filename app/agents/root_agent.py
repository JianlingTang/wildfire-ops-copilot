from app.models.schemas import ChatRequest, ManualRunRequest
from app.runtime import get_runtime
from app.runtime.intents import classify_intent as _classify_intent


def run_daily() -> dict:
    return get_runtime().run_daily()


def run_manual(request: ManualRunRequest) -> dict:
    return get_runtime().run_manual(request)


def route_chat(request: ChatRequest) -> dict:
    return get_runtime().route_chat(request)


def classify_intent(message: str) -> str:
    return _classify_intent(message)
