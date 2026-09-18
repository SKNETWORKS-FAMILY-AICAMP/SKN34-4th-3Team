import pytest
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.core.config import Settings
from src.models import (
    ModelConfigurationError,
    configure_chat_model,
    get_embedding_model,
    get_llm,
)


class StructuredResult(BaseModel):
    value: str


def test_llm_factory_rejects_missing_configuration() -> None:
    with pytest.raises(ModelConfigurationError, match="LLM is not configured"):
        get_llm(Settings(_env_file=None))


def test_embedding_factory_rejects_missing_configuration() -> None:
    with pytest.raises(ModelConfigurationError, match="Embedding model is not configured"):
        get_embedding_model(Settings(_env_file=None))


def test_chat_model_options_survive_structured_output_setup() -> None:
    model = ChatOpenAI(model="gpt-5-mini", api_key="test-key", temperature=0)

    configured = configure_chat_model(
        model,
        reasoning_effort="low",
        max_completion_tokens=321,
    )
    request_model = configured.with_structured_output(StructuredResult).first.bound

    assert request_model.reasoning_effort == "low"
    assert request_model.max_tokens == 321
