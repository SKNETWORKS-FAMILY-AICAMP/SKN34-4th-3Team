"""Backend 전용 구조화 작업을 수행하는 LLM chain 모음."""

from __future__ import annotations

import json
from datetime import date as DateValue

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ConfigDict, Field

from src.data.contracts import VectorSearchResult
from src.rag.guardrails import validate_citation_numbers, validate_generated_text


class _GeneratedOutput(BaseModel):
    """정의되지 않은 필드를 거부하는 Backend 작업용 구조화 출력."""

    model_config = ConfigDict(extra="forbid")


class LegalBasisGeneration(_GeneratedOutput):
    """Backend 판정을 변경하지 않는 법령 근거 설명."""

    legal_basis: str
    cited_source_numbers: list[int]


class DeductibilityGeneration(_GeneratedOutput):
    """지출의 경비 인정 가능성 분석 결과."""

    deductible: bool
    confidence: float = Field(ge=0, le=1)
    basis: str
    cited_source_numbers: list[int]


class AnnouncementSummaryGeneration(_GeneratedOutput):
    """공고문 원문에서 추출한 구조화 요약."""

    target: str
    benefit: str
    period: str
    documents: str
    notes: str


class ReceiptExtractionGeneration(_GeneratedOutput):
    """영수증 이미지에서 확인한 필드."""

    date: DateValue | None = None
    vendor: str | None = None
    amount: int | None = Field(default=None, ge=0)
    items: list[str] = Field(default_factory=list)
    category: str | None = None


LEGAL_BASIS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Backend가 확정한 세액감면 판정을 절대로 변경하지 말고, 제공된 법령 근거만 "
            "사용해 한국어로 설명하세요. 근거에 없는 법령명, 조문, 비율, 요건을 만들지 "
            "마세요. cited_source_numbers에는 실제 사용한 근거 번호만 반환하세요.",
        ),
        (
            "human",
            "판정 eligible={eligible}\n판정 사유={reasons}\n조건={conditions}\n"
            "법령 근거:\n{evidence}",
        ),
    ]
)


DEDUCTIBILITY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "제공된 지출 정보와 세법 근거만 사용해 경비 인정 가능성을 분석하세요. "
            "확정 세무 판정처럼 표현하지 말고 증빙과 업무 관련성 확인 필요성을 포함하세요. "
            "confidence는 근거가 불명확할수록 낮추고 cited_source_numbers에는 실제 사용한 "
            "근거 번호만 반환하세요.",
        ),
        (
            "human",
            "지출 정보={expense}\n세법 근거:\n{evidence}",
        ),
    ]
)


ANNOUNCEMENT_SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "공고문 원문에 명시된 내용만 한국어로 구조화하세요. 원문에 없는 날짜, 금액, "
            "자격, 서류를 추정하지 마세요. 확인할 수 없는 필드는 빈 문자열로 반환하세요.",
        ),
        ("human", "공고문 원문:\n{raw_content}"),
    ]
)


async def generate_legal_basis(
    llm: BaseChatModel,
    *,
    eligible: bool,
    reasons: list[str],
    conditions: dict[str, object],
    evidence: list[VectorSearchResult],
) -> tuple[LegalBasisGeneration, tuple[int, ...]]:
    """Backend 판정과 검색 근거로 법령 설명을 생성하고 인용을 검증한다."""
    chain = LEGAL_BASIS_PROMPT | llm.with_structured_output(LegalBasisGeneration)
    result = LegalBasisGeneration.model_validate(
        await chain.ainvoke(
            {
                "eligible": eligible,
                "reasons": json.dumps(reasons, ensure_ascii=False),
                "conditions": json.dumps(conditions, ensure_ascii=False),
                "evidence": _format_evidence(evidence),
            },
            config={"run_name": "backend_legal_basis"},
        )
    )
    result = result.model_copy(
        update={
            "legal_basis": validate_generated_text(
                result.legal_basis,
                field_name="legal_basis",
            )
        }
    )
    citations = validate_citation_numbers(
        result.cited_source_numbers,
        source_count=len(evidence),
    )
    return result, citations


async def generate_deductibility(
    llm: BaseChatModel,
    *,
    expense: dict[str, object],
    evidence: list[VectorSearchResult],
) -> tuple[DeductibilityGeneration, tuple[int, ...]]:
    """지출 정보와 검색 근거로 경비 가능성을 생성하고 인용을 검증한다."""
    chain = DEDUCTIBILITY_PROMPT | llm.with_structured_output(
        DeductibilityGeneration
    )
    result = DeductibilityGeneration.model_validate(
        await chain.ainvoke(
            {
                "expense": json.dumps(expense, ensure_ascii=False),
                "evidence": _format_evidence(evidence),
            },
            config={"run_name": "backend_deductibility"},
        )
    )
    result = result.model_copy(
        update={
            "basis": validate_generated_text(result.basis, field_name="basis")
        }
    )
    citations = validate_citation_numbers(
        result.cited_source_numbers,
        source_count=len(evidence),
    )
    return result, citations


async def summarize_announcement(
    llm: BaseChatModel,
    *,
    raw_content: str,
) -> AnnouncementSummaryGeneration:
    """공고문 원문을 구조화하고 필수 생성 문자열을 정규화한다."""
    chain = ANNOUNCEMENT_SUMMARY_PROMPT | llm.with_structured_output(
        AnnouncementSummaryGeneration
    )
    result = AnnouncementSummaryGeneration.model_validate(
        await chain.ainvoke(
            {"raw_content": raw_content},
            config={"run_name": "backend_announcement_summary"},
        )
    )
    return result.model_copy(
        update={
            field_name: getattr(result, field_name).strip()
            for field_name in ("target", "benefit", "period", "documents", "notes")
        }
    )


async def extract_receipt(
    llm: BaseChatModel,
    *,
    image_data_url: str,
) -> ReceiptExtractionGeneration:
    """Vision 입력에서 영수증 필드를 추출한다."""
    structured_model = llm.with_structured_output(ReceiptExtractionGeneration)
    prompt = ChatPromptTemplate.from_messages(
        [
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": (
                            "영수증 이미지에서 직접 확인되는 거래일, 상호, 총액, 품목을 "
                            "추출하세요. 확인할 수 없는 값은 null 또는 빈 배열로 반환하고 "
                            "값을 추정하지 마세요. category는 확인된 품목을 바탕으로 짧은 "
                            "한국어 지출 분류를 반환하세요."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                ]
            )
        ]
    )
    result = await (prompt | structured_model).ainvoke(
        {},
        config={"run_name": "backend_receipt_ocr"},
    )
    return ReceiptExtractionGeneration.model_validate(result)


def _format_evidence(documents: list[VectorSearchResult]) -> str:
    """검색 문서를 LLM이 인용할 수 있는 번호 문맥으로 변환한다."""
    return "\n\n".join(
        (
            f"[{index}] title={document['title']} source={document['source']} "
            f"page={document['page']}\n{document['content']}"
        )
        for index, document in enumerate(documents, start=1)
    )
