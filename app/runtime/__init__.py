from __future__ import annotations

import os

from app.runtime.adk import AdkRuntime
from app.runtime.base import AgentRuntime
from app.runtime.mock_demo import MockDemoRuntime


def get_runtime() -> AgentRuntime:
    runtime_name = os.getenv("AGENT_RUNTIME", "adk").lower()
    if runtime_name == "mock_demo":
        return MockDemoRuntime()
    return AdkRuntime()
