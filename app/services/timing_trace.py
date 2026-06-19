from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Any


class TimingTrace:
    def __init__(self) -> None:
        self.started_at = perf_counter()
        self.steps: list[dict[str, Any]] = []

    @contextmanager
    def step(self, name: str, **detail: Any) -> Iterator[None]:
        started_at = perf_counter()
        status = "completed"
        error: dict[str, str] | None = None
        try:
            yield
        except Exception as exc:
            status = "failed"
            error = {"type": exc.__class__.__name__, "message": str(exc)}
            raise
        finally:
            step_detail = {key: value for key, value in detail.items() if value is not None}
            if error:
                step_detail["error"] = error
            self.steps.append(
                {
                    "name": name,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                    "status": status,
                    "detail": step_detail,
                }
            )

    def snapshot(self) -> dict[str, Any]:
        return {
            "total_ms": round((perf_counter() - self.started_at) * 1000, 2),
            "steps": self.steps,
        }
