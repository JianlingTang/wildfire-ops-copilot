from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.schemas import ChatRequest, ManualRunRequest


class AgentRuntime(ABC):
    @abstractmethod
    def run_daily(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def run_manual(self, request: ManualRunRequest) -> dict:
        raise NotImplementedError

    @abstractmethod
    def route_chat(self, request: ChatRequest) -> dict:
        raise NotImplementedError
