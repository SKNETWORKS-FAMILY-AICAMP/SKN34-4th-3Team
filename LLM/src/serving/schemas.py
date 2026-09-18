from __future__ import annotations

from datetime import date as DateValue
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.rag.answer import AnswerStatus
from src.rag.roadmap import RoadmapStep


ComponentState = Literal[
    "configured",
    "not_configured",
    "mock",
    "in_memory",
    "postgres",
]


class ComponentConfiguration(BaseModel):
    """Health 응답에 포함할 구성요소별 설정 상태."""

    llm: ComponentState
    embedding: ComponentState
    data_source: ComponentState


class HealthResponse(BaseModel):
    """LLM API 프로세스 Health 응답."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    components: ComponentConfiguration


class EligibilityDecisionRequest(BaseModel):
    """Backend가 확정해 LLM에 전달하는 자격 판정 결과."""

    eligible: bool
    reasons: list[str]


class RagAnswerRequest(BaseModel):
    """특정 정책 근거 답변을 요청하는 내부 API 본문."""

    question: str
    policy_id: int | None = None
    top_k: int | None = None
    decision: EligibilityDecisionRequest | None = None
    user_id: int | None = None
    user_context: BackendUserContext | None = None


class SourceResponse(BaseModel):
    """RAG 답변에서 사용자에게 제공할 Chunk 출처."""

    chunk_id: str
    policy_id: int | None
    title: str
    source: str
    page: int
    excerpt: str
    score: float


class RagAnswerResponse(BaseModel):
    """특정 정책의 근거 기반 답변과 출처 응답."""

    answer: str
    route: Literal["policy", "notice", "tax"]
    status: AnswerStatus
    grounded: bool
    sources: list[SourceResponse]
    decision: EligibilityDecisionRequest | None = None
    guardrail_reason: Literal[
        "out_of_scope",
        "insufficient_evidence",
        "generation_validation_failed",
    ] | None = None


class BackendUserContext(BaseModel):
    """Backend가 인증된 사용자에서 조립해 전달하는 개인·사업자 Context."""

    model_config = ConfigDict(extra="forbid")

    userId: int = Field(gt=0)
    age: int | None = Field(default=None, ge=0, le=150)
    region: str | None = None
    businessType: str | None = None
    industry: str | None = None
    businessRegisteredAt: str | None = None
    foundedAt: str | None = None


class BackendNoticeResult(BaseModel):
    """Backend DB 조회가 LLM Notice branch에 전달하는 실제 공고."""

    model_config = ConfigDict(extra="forbid")

    announcementId: int = Field(gt=0)
    policyId: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1)
    content: str | None = None
    benefit: str | None = None
    sourceUrl: str | None = None
    applyStartDate: DateValue | None = None
    applyEndDate: DateValue | None = None


class ConversationHistoryMessage(BaseModel):
    """완료된 과거 대화에서 Backend가 전달하는 단일 메시지."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """공백뿐인 메시지를 거부하고 원문의 앞뒤 공백만 제거한다."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("conversation history content must not be blank")
        return normalized


class RagChatRequest(BaseModel):
    """Backend `POST /rag/chat` 호출 계약."""

    category: Literal["tax", "expense", "saving", "policy", "roadmap"]
    question: str
    roadmapStep: RoadmapStep | None = None
    userContext: BackendUserContext | None = None
    noticeResults: list[BackendNoticeResult] | None = None
    conversationHistory: list[ConversationHistoryMessage] = Field(
        default_factory=list,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_conversation_history(self) -> "RagChatRequest":
        """완료된 user/assistant 쌍과 전체 문맥 크기를 검증한다."""
        if self.category != "roadmap" and self.roadmapStep is not None:
            raise ValueError("roadmapStep is only valid for roadmap category")
        history = self.conversationHistory
        if len(history) % 2:
            raise ValueError("conversation history must contain completed pairs")
        for index, message in enumerate(history):
            expected_role = "user" if index % 2 == 0 else "assistant"
            if message.role != expected_role:
                raise ValueError(
                    "conversation history roles must alternate user and assistant"
                )
        if sum(len(message.content) for message in history) > 12000:
            raise ValueError("conversation history must not exceed 12000 characters")
        return self


class RagChatSource(BaseModel):
    """Backend가 answer_sources에 저장하는 출처 형식."""

    title: str
    url: str
    source: str
    excerpt: str


class RagChatResponse(BaseModel):
    """Backend 챗봇 어댑터에 반환하는 Graph 응답."""

    answer: str
    sources: list[RagChatSource]
    grounded: bool
    route: Literal["policy", "notice", "tax", "roadmap"]
    status: AnswerStatus
    guardrail_reason: Literal[
        "out_of_scope",
        "insufficient_evidence",
        "generation_validation_failed",
    ] | None = None


class TaxReductionConditions(BaseModel):
    """Backend가 세액감면 판정에 사용한 사용자·사업자 조건."""

    age: int | None = None
    region: str | None = None
    industry: str | None = None
    businessRegisteredAt: str | None = None
    foundedAt: str | None = None


class LegalBasisRequest(BaseModel):
    """Backend가 확정한 판정의 법령 근거 설명 요청."""

    eligible: bool
    reasons: list[str]
    conditions: TaxReductionConditions = Field(
        default_factory=TaxReductionConditions
    )


class LegalBasisResponse(BaseModel):
    """Backend 판정을 보존한 근거 설명 응답."""

    reasons: list[str]
    legalBasis: str
    sources: list[RagChatSource]
    grounded: bool
    status: AnswerStatus
    llmUsed: bool


class ReceiptExtractionResponse(BaseModel):
    """Vision 모델이 영수증에서 직접 확인한 필드."""

    date: DateValue | None = None
    vendor: str | None = None
    amount: int | None = Field(default=None, ge=0)
    items: list[str] = Field(default_factory=list)
    category: str | None = None
    source: Literal["vision"] = "vision"
    llmUsed: bool = True


class DeductibilityRequest(BaseModel):
    """경비 인정 가능성 분석에 필요한 지출 정보."""

    category: str = Field(min_length=1)
    amount: int = Field(ge=0)
    vendor: str = Field(min_length=1)
    items: list[str] = Field(default_factory=list)


class DeductibilityResponse(BaseModel):
    """세법 근거에 제한된 경비 인정 가능성 분석."""

    deductible: bool
    confidence: float = Field(ge=0, le=1)
    basis: str
    sources: list[RagChatSource]
    grounded: bool
    status: AnswerStatus
    llmUsed: bool


class AnnouncementSummaryRequest(BaseModel):
    """Backend가 전달한 공고문 원문과 출처."""

    rawContent: str = Field(min_length=1)
    source: str = ""


class AnnouncementSummaryResponse(BaseModel):
    """공고문 원문에서만 추출한 구조화 요약."""

    target: str
    benefit: str
    period: str
    documents: str
    notes: str
    source: str
    llmUsed: bool


class RagReindexRequest(BaseModel):
    """Backend 관리자 재색인 요청 계약."""

    documentIds: list[int] = Field(default_factory=list)
    force: bool = False


class PolicyRecommendationRequest(BaseModel):
    """사용자 프로필 기반 전체 정책 탐색 요청."""

    user_id: int
    question: str
    top_k: int | None = None


class MatchedPolicyResponse(BaseModel):
    """검색된 정책과 해당 정책을 뒷받침하는 출처 목록."""

    policy_id: int
    title: str
    sources: list[SourceResponse]


class PolicyRecommendationResponse(BaseModel):
    """사용자 조건과 관련된 정책 탐색·요약 응답."""

    user_id: int
    answer: str
    grounded: bool
    policies: list[MatchedPolicyResponse]
    guardrail_reason: Literal[
        "out_of_scope",
        "insufficient_evidence",
        "generation_validation_failed",
    ] | None = None


class IndexRequest(BaseModel):
    """로컬 캐시 무시 여부를 지정하는 인덱스 준비 요청."""

    force: bool = False


class IndexResponse(BaseModel):
    """인덱스 준비 결과와 캐시 또는 Embedding 출처 정보."""

    status: Literal["ready", "already_ready"]
    source: Literal["cache", "embedding"]
    document_count: int
    chunk_count: int
    requested_document_ids: list[int] = Field(default_factory=list)


class ReadyResponse(BaseModel):
    """현재 프로세스의 RAG 요청 처리 준비 상태."""

    status: Literal["ready", "not_ready"]
    index_ready: bool
    llm_configured: bool
    embedding_configured: bool
    langsmith_tracing: bool
    document_count: int
    chunk_count: int
    index_source: Literal["cache", "embedding"] | None
