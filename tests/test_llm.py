"""Тесты LLM-провайдеров."""

from __future__ import annotations

from osa.llm.base import LLMMessage


def test_stub_provider_returns_configured_text() -> None:
    """Stub возвращает заранее заданный текст (без scenario)."""
    from osa.llm.stub import StubProvider

    provider = StubProvider(default_response_text="hello back", tokens=42)
    messages = [LLMMessage(role="user", content="hi")]
    response = provider.complete(messages)

    assert response.content == "hello back"
    assert response.tokens_used == 42
    assert response.model == "stub-1"


def test_stub_provider_records_calls() -> None:
    """Stub записывает вызовы для проверки в тестах."""
    from osa.llm.stub import StubProvider

    provider = StubProvider()
    provider.complete([LLMMessage(role="user", content="a")])
    provider.complete([LLMMessage(role="user", content="b")])

    assert provider.call_count == 2
    assert provider.last_messages[0].content == "b"


def test_resolve_api_key_from_env(monkeypatch) -> None:
    """resolve_api_key берёт ключ из env если в конфиге нет."""
    from osa.llm.base import resolve_api_key

    monkeypatch.setenv("OSA_LLM__API_KEY", "from-env-1")
    assert resolve_api_key(None) == "from-env-1"

    monkeypatch.delenv("OSA_LLM__API_KEY")
    monkeypatch.setenv("OSA_LLM_API_KEY", "from-env-2")
    assert resolve_api_key(None) == "from-env-2"

    monkeypatch.delenv("OSA_LLM_API_KEY")
    assert resolve_api_key(None) == ""


def test_resolve_api_key_from_config() -> None:
    """resolve_api_key приоритизирует значение из конфига."""
    from osa.llm.base import resolve_api_key

    assert resolve_api_key("from-config") == "from-config"
