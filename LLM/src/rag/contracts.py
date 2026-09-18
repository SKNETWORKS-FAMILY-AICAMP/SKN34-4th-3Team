from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.data.contracts import VectorSearchResult


GuardrailReason = Literal[
    "out_of_scope",
    "insufficient_evidence",
    "generation_validation_failed",
]


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    """Backend가 확정한 자격 판정 결과."""

    eligible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceCitation:
    """사용자에게 반환할 검색 근거와 출처 정보."""

    chunk_id: str
    policy_id: int | None
    title: str
    source: str
    page: int
    excerpt: str
    score: float

    @classmethod
    def from_search_result(
        cls,
        search_result: VectorSearchResult,
    ) -> "SourceCitation":
        """Vector 검색 결과를 출처 인용 객체로 변환한다.

        Args:
            search_result: Chunk 본문, 출처 metadata와 유사도 점수를 담은 검색 결과.

        Returns:
            공백을 정규화한 500자 근거 문구를 포함하는 SourceCitation 객체.
        """
        normalized_excerpt = " ".join(search_result["content"].split())[:500]
        return cls(
            chunk_id=search_result["chunk_id"],
            policy_id=search_result["policy_id"],
            title=search_result["title"],
            source=search_result["source"],
            page=search_result["page"],
            excerpt=normalized_excerpt,
            score=search_result["score"],
        )


@dataclass(frozen=True, slots=True)
class RagAnswer:
    """특정 정책 질의에 대한 답변·출처·판정 보존 결과."""

    answer: str
    grounded: bool
    sources: tuple[SourceCitation, ...]
    decision: EligibilityDecision | None = None
    guardrail_reason: GuardrailReason | None = None


@dataclass(frozen=True, slots=True)
class MatchedPolicy:
    """사용자 질문과 관련된 정책과 해당 검색 근거 묶음."""

    policy_id: int
    title: str
    sources: tuple[SourceCitation, ...]


@dataclass(frozen=True, slots=True)
class PolicyDiscoveryAnswer:
    """사용자 프로필 기반 전체 정책 탐색 결과."""

    user_id: int
    answer: str
    grounded: bool
    policies: tuple[MatchedPolicy, ...]
    guardrail_reason: GuardrailReason | None = None


class GeneratedOutput(BaseModel):
    """정의되지 않은 필드를 거부하는 LLM 구조화 출력의 공통 기반."""

    model_config = ConfigDict(extra="forbid")


class GeneratedGroundedAnswer(GeneratedOutput):
    """특정 정책 답변에 필요한 LLM 구조화 출력."""

    answer: str = Field(description="결론부터 3~5문장으로 작성한 간결한 근거 답변")
    cited_source_numbers: list[int] = Field(
        description="답변에 실제 사용한 1부터 시작하는 출처 번호"
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="가장 중요한 근거 부족 또는 추가 확인 안내 한 개",
    )


class GeneratedPolicyItem(GeneratedOutput):
    """검색된 정책 하나에 대한 LLM 요약과 출처 참조."""

    policy_id: int = Field(description="검색 문맥에 실제 존재하는 정책 ID")
    summary: str = Field(description="문서 근거에 한정한 두 문장 이내의 정책 요약")
    eligibility_requirements: list[str] = Field(
        default_factory=list,
        description="공식 문서에서 확인한 지원 자격 조건",
    )
    exclusion_conditions: list[str] = Field(
        default_factory=list,
        description="공식 문서에서 확인한 참여 제한 또는 제외 조건",
    )
    support_details: list[str] = Field(
        default_factory=list,
        description="공식 문서에서 확인한 지원 금액 또는 핵심 지원 내용",
    )
    application_period: str | None = Field(
        default=None,
        description="공식 문서에서 확인한 신청기간 또는 마감일",
    )
    relevance_reasons: list[str] = Field(
        default_factory=list,
        description="사용자 조건·질문과 정책이 관련된 핵심 이유 최대 2개",
    )
    requirements_to_verify: list[str] = Field(
        default_factory=list,
        description="사용자가 별도로 확인해야 할 핵심 조건 최대 2개",
    )
    cited_source_numbers: list[int] = Field(
        description="이 정책 요약에 실제 사용한 출처 번호"
    )


class GeneratedPolicyDiscovery(GeneratedOutput):
    """사용자 프로필 기반 정책 탐색의 LLM 구조화 출력."""

    overview: str = Field(description="검색된 관련 정책 전체에 대한 한 문장 안내")
    policies: list[GeneratedPolicyItem] = Field(
        description="관련성이 높은 순서의 정책별 요약 최대 3개"
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="자격 비확정 또는 추가 확인 필요성을 알리는 핵심 안내 한 개",
    )
