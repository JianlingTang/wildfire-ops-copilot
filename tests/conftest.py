from collections.abc import Generator

import pytest

from app.services.analysis_pipeline import reset_analysis_cache
from app.services.firestore_store import store


@pytest.fixture(autouse=True)
def force_demo_external_data(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("WILDFIRE_DATA_MODE", "demo")
    yield


@pytest.fixture(autouse=True)
def reset_store() -> Generator[None, None, None]:
    store.reset()
    reset_analysis_cache()
    yield
    store.reset()
    reset_analysis_cache()
