import pytest


@pytest.fixture(autouse=True)
def offline_by_default(monkeypatch):
    # Tests never call a real model: Agent() uses the phrase rules unless a test
    # injects a stubbed LLM interpreter (tests/test_llm_interpreter.py).
    monkeypatch.setenv("STELLAR_INTERPRETER", "rules")
