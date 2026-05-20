import pytest


@pytest.fixture(autouse=True)
def force_local_ai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_AI_PROVIDER", "local")
