import pytest
from pydantic import SecretStr, ValidationError

from src.core.config import Settings


def test_llm_default_port_matches_backend_contract() -> None:
    assert Settings(_env_file=None).port == 8001


def test_placeholder_values_are_not_treated_as_configured() -> None:
    settings = Settings(
        _env_file=None,
        llm_model="YOUR_LLM_MODEL",
        embedding_model="YOUR_EMBEDDING_MODEL",
        openai_api_key=SecretStr("YOUR_OPENAI_API_KEY"),
    )

    assert settings.llm_configured is False
    assert settings.embedding_configured is False


def test_openai_configuration_is_detected_without_exposing_secret() -> None:
    settings = Settings(
        _env_file=None,
        llm_model="test-chat-model",
        embedding_model="test-embedding-model",
        openai_api_key=SecretStr("test-secret"),
    )

    assert settings.llm_configured is True
    assert settings.embedding_configured is True
    assert "test-secret" not in repr(settings)


def test_cohere_configuration_is_detected_without_exposing_secret() -> None:
    settings = Settings(
        _env_file=None,
        cohere_api_key=SecretStr("cohere-secret"),
    )

    assert settings.cohere_configured is True
    assert settings.cohere_rerank_model == "rerank-v4.0-fast"
    assert "cohere-secret" not in repr(settings)


def test_database_components_are_used_when_url_is_placeholder() -> None:
    settings = Settings(
        _env_file=None,
        database_url=SecretStr("YOUR_DATABASE_URL"),
        postgres_user="admin",
        postgres_password=SecretStr("database-secret"),
        postgres_db="startup_platform",
        db_host="localhost",
    )

    assert settings.database_configured is True
    assert "database-secret" not in repr(settings)


def test_cors_origins_are_parsed_from_comma_separated_setting() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins="http://localhost:5173, http://127.0.0.1:5173",
    )

    assert settings.allowed_cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_guardrail_keywords_and_answer_are_configurable() -> None:
    settings = Settings(
        _env_file=None,
        rag_allowed_keywords="정책, 세금",
        rag_blocked_keywords="날씨, 파이썬",
        out_of_scope_answer="지원하지 않는 질문",
    )

    assert settings.allowed_rag_keywords == ("정책", "세금")
    assert settings.blocked_rag_keywords == ("날씨", "파이썬")
    assert settings.out_of_scope_answer == "지원하지 않는 질문"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"chunk_size": 0}, "CHUNK_SIZE must be at least 1"),
        ({"chunk_overlap": -1}, "CHUNK_OVERLAP must not be negative"),
        (
            {"chunk_size": 100, "chunk_overlap": 100},
            "CHUNK_OVERLAP must be smaller than CHUNK_SIZE",
        ),
        ({"default_top_k": 0}, "DEFAULT_TOP_K must be at least 1"),
        (
            {"min_relevance_score": 1.1},
            "MIN_RELEVANCE_SCORE must be between 0 and 1",
        ),
        ({"max_question_length": 0}, "MAX_QUESTION_LENGTH must be at least 1"),
        (
            {"max_context_characters": 0},
            "MAX_CONTEXT_CHARACTERS must be at least 1",
        ),
        (
            {"max_chunks_per_policy": 0},
            "MAX_CHUNKS_PER_POLICY must be at least 1",
        ),
        (
            {"hybrid_dense_candidate_k": 0},
            "HYBRID_DENSE_CANDIDATE_K must be at least 1",
        ),
        (
            {"hybrid_bm25_candidate_k": 0},
            "HYBRID_BM25_CANDIDATE_K must be at least 1",
        ),
        ({"hybrid_rrf_k": 0}, "HYBRID_RRF_K must be at least 1"),
        (
            {"cohere_rerank_candidate_k": 0},
            "COHERE_RERANK_CANDIDATE_K must be at least 1",
        ),
        ({"tax_max_hops": 0}, "TAX_MAX_HOPS must be at least 1"),
        (
            {"database_connect_timeout": 0},
            "DATABASE_CONNECT_TIMEOUT must be at least 1",
        ),
        ({"db_port": 0}, "DB_PORT must be between 1 and 65535"),
    ],
)
def test_invalid_rag_settings_are_rejected(
    overrides: dict[str, int | float],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **overrides)


def test_blank_invalid_generation_answer_is_rejected() -> None:
    with pytest.raises(ValidationError, match="INVALID_GENERATION_ANSWER"):
        Settings(_env_file=None, invalid_generation_answer="   ")
