from __future__ import annotations

import os

from app.runtime.base import AgentRuntime


def get_runtime() -> AgentRuntime:
    # Imported lazily: the concrete runtimes import app.services.chat_conversations, which
    # imports app.runtime.intents. Importing them here would make that a cycle, so any module
    # that reached app.runtime.intents first would fail.
    if os.getenv("AGENT_RUNTIME", "adk").lower() == "mock_demo":
        from app.runtime.mock_demo import MockDemoRuntime

        return MockDemoRuntime()

    from app.runtime.adk import AdkRuntime

    return AdkRuntime()
