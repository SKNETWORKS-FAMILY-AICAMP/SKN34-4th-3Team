import os

import pytest
from pydantic import SecretStr

from src.core.config import Settings
from src.core.langsmith import LangSmithConfigurationError, configure_langsmith


def test_disabled_tracing_does_not_create_a_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(**_kwargs: object) -> object:
        raise AssertionError("LangSmith client must not be created")

    monkeypatch.setattr("src.core.langsmith.Client", fail_if_called)
    runtime = configure_langsmith(Settings(_env_file=None, langsmith_tracing=False))

    assert runtime.enabled is False
    assert runtime.client is None
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_enabled_tracing_requires_an_api_key() -> None:
    settings = Settings(
        _env_file=None,
        langsmith_tracing=True,
        langsmith_api_key=None,
    )

    with pytest.raises(LangSmithConfigurationError, match="LANGSMITH_API_KEY"):
        configure_langsmith(settings)


def test_enabled_tracing_configures_client_without_exposing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("src.core.langsmith.Client", FakeClient)
    settings = Settings(
        _env_file=None,
        langsmith_tracing=True,
        langsmith_api_key=SecretStr("test-langsmith-key"),
    )

    runtime = configure_langsmith(settings)

    assert runtime.enabled is True
    assert captured["api_url"] == "https://api.smith.langchain.com"
    assert captured["hide_inputs"] is False
    assert captured["hide_outputs"] is False
    assert "test-langsmith-key" not in repr(settings)
