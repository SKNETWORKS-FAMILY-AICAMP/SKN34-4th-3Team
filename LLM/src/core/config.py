from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parents[2]
ROOT_ENV_FILE = PROJECT_DIR.parent / ".env"


def _has_real_value(value: str | SecretStr | None) -> bool:
    """설정값이 비어 있거나 예시용 placeholder인지 확인한다.

    Args:
        value: 검사할 일반 문자열, 비밀 문자열 또는 None.

    Returns:
        실제 설정값이 존재하면 True, 비어 있거나 `YOUR_`로 시작하면 False.
    """
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    if value is None:
        return False

    normalized = value.strip()
    return bool(normalized) and not normalized.upper().startswith("YOUR_")


class Settings(BaseSettings):
    """환경변수와 `.env`를 검증된 애플리케이션 설정으로 제공한다."""

    app_name: str = "policy-rag-llm"
    app_env: str = "local"
    host: str = "0.0.0.0"
    port: int = 8001
    reload: bool = False
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"

    llm_model: str = ""
    embedding_model: str = ""
    openai_api_key: SecretStr | None = None
    cohere_api_key: SecretStr | None = None
    cohere_rerank_model: str = "rerank-v4.0-fast"
    cohere_rerank_candidate_k: int = 20
    tax_max_hops: int = 3
    tax_cache_enabled: bool = True
    tax_cache_similarity_threshold: float = 0.95
    tax_cache_decision_similarity_threshold: float = 0.98
    database_url: SecretStr | None = None
    database_connect_timeout: int = 5
    vector_store_backend: Literal["postgres", "in_memory"] = "postgres"
    postgres_user: str = ""
    postgres_password: SecretStr | None = None
    postgres_db: str = ""
    db_host: str = "localhost"
    db_port: int = 5432

    chunk_size: int = 1000
    chunk_overlap: int = 150
    default_top_k: int = 5
    min_relevance_score: float = 0.2
    retrieval_mode: Literal["dense", "hybrid"] = "hybrid"
    hybrid_dense_candidate_k: int = 20
    hybrid_bm25_candidate_k: int = 20
    hybrid_rrf_k: int = 60
    max_question_length: int = 1000
    max_context_characters: int = 12000
    max_chunks_per_policy: int = 2
    rag_allowed_keywords: str = (
        "정책,지원,지원금,보조금,장려금,창업,청년,사업,공고,신청,자격,대상,혜택,"
        "세금,세무,세법,세액,감면,절세,경비,사업자,업종,지역,주거,취업,근속,"
        "직무,문화,이전비,받을,신고,납부,기간,마감,방법,서류,금액,얼마,언제,조건"
    )
    rag_blocked_keywords: str = (
        "파이썬,python,append,자바,javascript,코딩,프로그래밍,날씨,주식,비트코인,"
        "요리,레시피,게임"
    )
    out_of_scope_answer: str = "그 질문에는 답변할 수 없습니다"
    invalid_generation_answer: str = (
        "답변 근거를 정확히 확인하지 못했습니다. 다시 시도해 주세요."
    )
    vector_index_cache_path: Path = Path("data/processed/rag_vector_index.json")

    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "skn34-3rd-project"
    langsmith_api_key: SecretStr | None = None
    langsmith_hide_inputs: bool = False
    langsmith_hide_outputs: bool = False

    model_config = SettingsConfigDict(
        env_file=(ROOT_ENV_FILE, PROJECT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def llm_configured(self) -> bool:
        """LLM 모델명과 OpenAI API Key가 모두 설정됐는지 반환한다."""
        return _has_real_value(self.llm_model) and _has_real_value(
            self.openai_api_key
        )

    @property
    def embedding_configured(self) -> bool:
        """Embedding 모델명과 OpenAI API Key가 모두 설정됐는지 반환한다."""
        return _has_real_value(self.embedding_model) and _has_real_value(
            self.openai_api_key
        )

    @property
    def cohere_configured(self) -> bool:
        """Cohere Rerank 모델명과 API Key가 모두 설정됐는지 반환한다."""
        return _has_real_value(self.cohere_rerank_model) and _has_real_value(
            self.cohere_api_key
        )

    @property
    def database_configured(self) -> bool:
        """PostgreSQL 연결 문자열이 실제 값으로 설정됐는지 반환한다."""
        return _has_real_value(self.database_url) or all(
            (
                _has_real_value(self.postgres_user),
                _has_real_value(self.postgres_password),
                _has_real_value(self.postgres_db),
                _has_real_value(self.db_host),
            )
        )

    @property
    def allowed_cors_origins(self) -> list[str]:
        """쉼표로 구분된 CORS origin 설정을 목록으로 반환한다."""
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def langsmith_configured(self) -> bool:
        """활성화된 LangSmith 추적에 필요한 설정이 모두 있는지 반환한다."""
        return (
            self.langsmith_tracing
            and _has_real_value(self.langsmith_endpoint)
            and _has_real_value(self.langsmith_project)
            and _has_real_value(self.langsmith_api_key)
        )

    @property
    def resolved_vector_index_cache_path(self) -> Path:
        """프로젝트 기준 절대 Vector 인덱스 캐시 경로를 반환한다."""
        configured_cache_path = self.vector_index_cache_path
        return (
            configured_cache_path
            if configured_cache_path.is_absolute()
            else PROJECT_DIR / configured_cache_path
        )

    @property
    def allowed_rag_keywords(self) -> tuple[str, ...]:
        """쉼표로 구분된 RAG 허용 키워드를 정규화해 반환한다."""
        return tuple(
            keyword.strip()
            for keyword in self.rag_allowed_keywords.split(",")
            if keyword.strip()
        )

    @property
    def blocked_rag_keywords(self) -> tuple[str, ...]:
        """쉼표로 구분된 RAG 차단 키워드를 정규화해 반환한다."""
        return tuple(
            keyword.strip()
            for keyword in self.rag_blocked_keywords.split(",")
            if keyword.strip()
        )

    @model_validator(mode="after")
    def validate_rag_settings(self) -> Self:
        """Chunking·검색·Guardrail 설정값의 허용 범위를 검증한다.

        Returns:
            검증이 완료된 현재 설정 객체.

        Raises:
            ValueError: 설정값이 허용 범위를 벗어나거나 필수 문자열이 비었을 때.
        """
        if self.chunk_size < 1:
            raise ValueError("CHUNK_SIZE must be at least 1")
        if self.database_connect_timeout < 1:
            raise ValueError("DATABASE_CONNECT_TIMEOUT must be at least 1")
        if not 1 <= self.db_port <= 65535:
            raise ValueError("DB_PORT must be between 1 and 65535")
        if self.chunk_overlap < 0:
            raise ValueError("CHUNK_OVERLAP must not be negative")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.default_top_k < 1:
            raise ValueError("DEFAULT_TOP_K must be at least 1")
        if not 0 <= self.min_relevance_score <= 1:
            raise ValueError("MIN_RELEVANCE_SCORE must be between 0 and 1")
        if self.hybrid_dense_candidate_k < 1:
            raise ValueError("HYBRID_DENSE_CANDIDATE_K must be at least 1")
        if self.hybrid_bm25_candidate_k < 1:
            raise ValueError("HYBRID_BM25_CANDIDATE_K must be at least 1")
        if self.hybrid_rrf_k < 1:
            raise ValueError("HYBRID_RRF_K must be at least 1")
        if self.cohere_rerank_candidate_k < 1:
            raise ValueError("COHERE_RERANK_CANDIDATE_K must be at least 1")
        if self.tax_max_hops < 1:
            raise ValueError("TAX_MAX_HOPS must be at least 1")
        if not 0 <= self.tax_cache_similarity_threshold <= 1:
            raise ValueError("TAX_CACHE_SIMILARITY_THRESHOLD must be between 0 and 1")
        if not 0 <= self.tax_cache_decision_similarity_threshold <= 1:
            raise ValueError(
                "TAX_CACHE_DECISION_SIMILARITY_THRESHOLD must be between 0 and 1"
            )
        if (
            self.tax_cache_decision_similarity_threshold
            < self.tax_cache_similarity_threshold
        ):
            raise ValueError(
                "TAX_CACHE_DECISION_SIMILARITY_THRESHOLD must be greater than or "
                "equal to TAX_CACHE_SIMILARITY_THRESHOLD"
            )
        if self.max_question_length < 1:
            raise ValueError("MAX_QUESTION_LENGTH must be at least 1")
        if self.max_context_characters < 1:
            raise ValueError("MAX_CONTEXT_CHARACTERS must be at least 1")
        if self.max_chunks_per_policy < 1:
            raise ValueError("MAX_CHUNKS_PER_POLICY must be at least 1")
        if not self.allowed_rag_keywords:
            raise ValueError("RAG_ALLOWED_KEYWORDS must contain at least one keyword")
        if not self.out_of_scope_answer.strip():
            raise ValueError("OUT_OF_SCOPE_ANSWER must not be blank")
        if not self.invalid_generation_answer.strip():
            raise ValueError("INVALID_GENERATION_ANSWER must not be blank")
        return self


@lru_cache
def get_settings() -> Settings:
    """캐시된 애플리케이션 설정 객체를 반환한다.

    Returns:
        `LLM/.env`와 시스템 환경변수에서 읽은 Settings 객체.

    Notes:
        프로세스에서 한 번 생성한 설정을 재사용하므로 `.env` 변경 후에는 서버를
        재시작해야 한다.
    """
    return Settings()
