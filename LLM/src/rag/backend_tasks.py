"""Backend 전용 구조화 작업을 수행하는 LLM chain 모음."""

from __future__ import annotations

import json
from datetime import date as DateValue
from typing import Literal

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


class BusinessPlanSectionGeneration(_GeneratedOutput):
    """생성된 사업계획서 항목 하나."""

    key: str
    label: str
    content: str


class BusinessPlanGeneration(_GeneratedOutput):
    """사용자가 입력한 정보만으로 작성한 사업계획서 초안.

    지원사업 공고 양식을 받았으면 그 항목 구성을, 받지 못했으면 기본 PSST 4항목을 따른다.
    """

    sections: list[BusinessPlanSectionGeneration]
    summary: str


class BusinessPlanRefinement(_GeneratedOutput):
    businessName: str
    tagline: str
    targetCustomer: str
    problem: str
    solution: str
    differentiator: str
    team: str
    extraNotes: str


BUSINESS_PLAN_REFINE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "사업계획서 입력을 읽기 쉬운 한국어로 한 번 정리하세요. 입력된 사실만 유지하고 "
     "수치·실적·팀 이력 등 새 사실을 만들어 넣지 마세요. 비어 있는 필드는 빈 문자열로 두고, "
     "각 필드의 의미를 바꾸거나 서로 다른 사실을 합치지 마세요."),
    ("human", "{fields_json}"),
])


async def refine_business_plan_input(llm: BaseChatModel, fields: dict[str, str]) -> BusinessPlanRefinement:
    chain = BUSINESS_PLAN_REFINE_PROMPT | llm.with_structured_output(BusinessPlanRefinement)
    result = BusinessPlanRefinement.model_validate(await chain.ainvoke(
        {"fields_json": json.dumps(fields, ensure_ascii=False)},
        config={"run_name": "backend_business_plan_refine"},
    ))
    return result.model_copy(update={
        key: getattr(result, key).strip() if fields.get(key, "").strip() else ""
        for key in fields
    })


class BusinessPlanSectionScore(_GeneratedOutput):
    """항목 하나에 대한 예비진단 결과."""

    key: str
    label: str
    score: int = Field(ge=0, le=100)
    strengths: str
    improvements: str


class BusinessPlanEvaluation(_GeneratedOutput):
    """사업계획서 초안에 대한 AI 예비진단(자체 채점)."""

    overall_score: int = Field(ge=0, le=100)
    overall_comment: str
    sections: list[BusinessPlanSectionScore]


class ReceiptExtractionGeneration(_GeneratedOutput):
    """영수증 이미지에서 확인한 필드."""

    date: DateValue | None = None
    vendor: str | None = None
    amount: int | None = Field(default=None, ge=0)
    items: list[str] = Field(default_factory=list)
    category: str | None = None
    proof_type: Literal[
        "tax_invoice", "card_receipt", "cash_receipt", "simple_receipt", "unknown"
    ] = "unknown"
    # 값을 읽어낸 근거: 영수증에 인쇄된 글자를 그대로 옮긴 것. 화면에서 "이 문구를 보고 판단했다"를 보여준다.
    date_text: str | None = None
    vendor_text: str | None = None
    amount_text: str | None = None
    proof_evidence: str | None = None


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


_RECEIPT_CATEGORY_RULES = (
    "category는 확인된 품목·상호를 바탕으로 다음 중 정확히 하나만 반환하세요: "
    "사무용품, 통신비, 차량유지비, 광고선전비, 임차료, 복리후생비, 접대비, 교육·도서, 기타. "
    "식당·카페 영수증은 복리후생비로 하고(거래처 접대인지는 알 수 없습니다), "
    "어디에도 확실히 맞지 않으면 기타로 하세요."
)

_RECEIPT_PROOF_RULES = (
    "proof_type에는 이 증빙의 종류를 판별해 다음 중 하나로 반환하세요"
    "(실제로 보이는 표시만 근거로 판단하고 짐작하지 마세요):\n"
    "- tax_invoice: '세금계산서' 또는 '계산서'라는 문서 제목이 보임\n"
    "- card_receipt: '신용카드 매출전표', 카드 승인번호, 카드사명 등 카드 결제 표시가 보임\n"
    "- cash_receipt: '현금영수증'이라는 문서 제목이나 현금영수증 승인번호가 보임\n"
    "- simple_receipt: 위 표시 없이 품목·금액만 있는 일반 간이영수증으로 보임\n"
    "- unknown: 증빙 종류를 판별할 수 없음"
)


BUSINESS_PLAN_DEFAULT_SECTIONS_INSTRUCTION = (
    "정해진 PSST 4항목 구조를 그대로 쓰세요. 항목은 이 순서와 key·label을 정확히 그대로 "
    "사용하세요:\n"
    '1. key="problem", label="Problem · 문제인식" — 어떤 고객이 어떤 문제를 겪고 있는지, '
    "왜 지금 해결해야 하는지\n"
    '2. key="solution", label="Solution · 실현가능성" — 그 문제를 어떻게 해결하는지, '
    "제품·서비스의 핵심 기능과 차별점\n"
    '3. key="scaleUp", label="Scale-up · 성장전략" — 목표 시장 크기와 고객 확보 방법, '
    "수익모델을 어떻게 키울지\n"
    '4. key="team", label="Team · 팀구성" — 팀 구성과 이 팀이 이 사업을 해낼 수 있는 이유'
)

BUSINESS_PLAN_TEMPLATE_SECTIONS_INSTRUCTION = (
    "아래 '지원사업 공고 양식' 원문에 나온 사업계획서 항목 구성을 그대로 따르세요. 양식에 "
    "적힌 항목 제목을 label로 쓰고, 그 항목이 요구하는 내용을 content로 채우세요. key는 "
    '항목 순서를 나타내는 짧은 영문 소문자 식별자로 만드세요(예: "section_1", "section_2"). '
    "항목 개수와 순서는 양식과 최대한 똑같이 맞추고, 양식에 없는 항목을 새로 만들지 마세요.\n\n"
    "[지원사업 공고 양식]\n{template_text}"
)


BUSINESS_PLAN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "예비창업패키지 등 정부 지원사업에 내는 사업계획서 초안을 작성하는 보조 도구다. "
            "사용자가 입력한 정보만 근거로 쓰고, 매출액·투자 유치액·이용자 수 같은 구체적인 "
            "수치나 실적은 사용자가 주지 않았다면 만들어 내지 마세요. 대신 "
            "'정보 부족: 예상 매출액'처럼 빈 자리로 표시하세요. 각 항목의 content는 "
            "한국어로 2~4문장, 존댓말로 쓰세요.\n\n"
            "sections 항목 구성:\n{sections_instruction}\n\n"
            "summary는 sections 전체 내용을 3문장으로 압축한 요약입니다.",
        ),
        (
            "human",
            "사업명: {business_name}\n한 줄 소개: {tagline}\n목표 고객: {target_customer}\n"
            "핵심 문제: {problem_input}\n해결 방안: {solution_input}\n차별점: {differentiator}\n"
            "팀 구성: {team_input}\n신청하려는 지원사업(선택): {target_program}\n"
            "추가로 참고할 내용(선택): {extra_notes}\n공고 평가 기준(있는 경우): {announcement_criteria}",
        ),
    ]
)


async def generate_business_plan(
    llm: BaseChatModel,
    *,
    business_name: str,
    tagline: str,
    target_customer: str,
    problem_input: str,
    solution_input: str,
    differentiator: str,
    team_input: str,
    target_program: str,
    extra_notes: str,
    template_text: str = "",
    template_fields: list[str] | None = None,
    announcement_criteria: str = "",
) -> BusinessPlanGeneration:
    """사용자가 입력한 사업 정보로 사업계획서 초안을 생성한다.

    template_text가 있으면 그 지원사업 공고 양식의 항목 구성을 따르고, 없으면 기본
    PSST 4항목(문제인식·실현가능성·성장전략·팀구성) 구조로 만든다.
    """
    sections_instruction = (
        "다음 양식의 입력 항목을 같은 순서·이름으로 각각 한 번씩 작성하세요. "
        "key는 section_1, section_2처럼 순서대로 지정하세요. "
        "필요한 정보가 없으면 content를 '정보 부족'으로 적으세요:\n"
        + "\n".join(f"{index}. {name}" for index, name in enumerate(template_fields, 1))
        if template_fields else
        BUSINESS_PLAN_TEMPLATE_SECTIONS_INSTRUCTION.format(template_text=template_text.strip())
        if template_text and template_text.strip()
        else BUSINESS_PLAN_DEFAULT_SECTIONS_INSTRUCTION
    )
    chain = BUSINESS_PLAN_PROMPT | llm.with_structured_output(BusinessPlanGeneration)
    result = BusinessPlanGeneration.model_validate(
        await chain.ainvoke(
            {
                "sections_instruction": sections_instruction,
                "business_name": business_name or "(입력 없음)",
                "tagline": tagline or "(입력 없음)",
                "target_customer": target_customer or "(입력 없음)",
                "problem_input": problem_input or "(입력 없음)",
                "solution_input": solution_input or "(입력 없음)",
                "differentiator": differentiator or "(입력 없음)",
                "team_input": team_input or "(입력 없음)",
                "target_program": target_program or "(입력 없음)",
                "extra_notes": extra_notes or "(없음)",
                "announcement_criteria": announcement_criteria or "(없음)",
            },
            config={"run_name": "backend_business_plan"},
        )
    )
    if template_fields:
        by_label = {section.label.strip(): section for section in result.sections}
        result = result.model_copy(update={"sections": [
            BusinessPlanSectionGeneration(
                key=f"section_{index}", label=name,
                content=(by_label[name].content if name in by_label else "정보 부족"),
            ) for index, name in enumerate(template_fields, 1)
        ]})
    return result.model_copy(
        update={
            "sections": [
                section.model_copy(
                    update={
                        "content": validate_generated_text(
                            section.content, field_name=f"section:{section.key}"
                        )
                    }
                )
                for section in result.sections
            ],
            "summary": validate_generated_text(result.summary, field_name="summary"),
        }
    )


BUSINESS_PLAN_EVALUATE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "정부 R&D·창업지원사업 사업계획서 심사위원처럼, 아래 사업계획서 초안을 항목별로 "
            "평가하세요. 이것은 예비진단이며 실제 합격을 보장하지 않는다는 전제로, 초안에 "
            "실제로 쓰인 내용만 근거로 채점하세요. '정보 부족'이나 '[직접 채워 주세요: ...]' "
            "항목은 아직 채워지지 않은 것으로 보고 감점 사유로 다루세요. 점수는 내용의 "
            "구체성·논리적 연결·실현 가능성을 기준으로 0~100점, 5점 단위 권장. sections에는 "
            "아래에 주어진 항목을 모두, 주어진 순서 그대로, 같은 key·label로 반환하세요. 각 "
            "항목의 strengths(잘된 점)와 improvements(보완할 점)는 1~2문장, 존댓말로 구체적으로 "
            "쓰세요. overall_comment는 전체를 한두 문장으로 평가하세요. "
            "공고·양식에 평가 기준이 있으면 그것을 우선 적용하고, 없으면 구체성·논리성·실현 가능성을 적용하세요.\n"
            "공고 기준: {announcement_criteria}\n양식 기준: {template_criteria}",
        ),
        ("human", "{sections_text}"),
    ]
)


async def evaluate_business_plan(
    llm: BaseChatModel,
    *,
    sections: list[dict],
    announcement_criteria: str = "",
    template_criteria: str = "",
) -> BusinessPlanEvaluation:
    """작성된 초안을 항목별로 채점하는 AI 예비진단. 합격 여부가 아니라 참고용 자체 점검이다."""
    sections_text = (
        "\n\n".join(
            f"[{section.get('label') or section.get('key')}]\n"
            f"{(section.get('content') or '').strip() or '(작성 안 됨)'}"
            for section in sections
        )
        or "(작성된 항목 없음)"
    )
    chain = BUSINESS_PLAN_EVALUATE_PROMPT | llm.with_structured_output(BusinessPlanEvaluation)
    result = BusinessPlanEvaluation.model_validate(
        await chain.ainvoke(
            {"sections_text": sections_text,
             "announcement_criteria": announcement_criteria or "(없음)",
             "template_criteria": template_criteria or "(없음)"},
            config={"run_name": "backend_business_plan_evaluate"},
        )
    )
    return result.model_copy(
        update={"overall_comment": validate_generated_text(result.overall_comment, field_name="overall_comment")}
    )


async def extract_receipt(
    llm: BaseChatModel,
    *,
    image_data_url: str,
) -> ReceiptExtractionGeneration:
    """Vision 입력에서 영수증 필드를 추출한다. OCR을 쓸 수 없을 때의 대비 경로다."""
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
                            "값을 추정하지 마세요. "
                            + _RECEIPT_CATEGORY_RULES
                            + "\n\n"
                            + _RECEIPT_PROOF_RULES
                            + "\n\n또한 값을 읽어낸 근거를 남기세요. date_text, vendor_text, "
                            "amount_text에는 각각 거래일·상호·총액을 읽은 자리의 인쇄 글자를 "
                            "이미지에 보이는 그대로 옮기고(예: '합계 45,000원'), proof_evidence에는 "
                            "proof_type을 그렇게 판단한 근거 문구(예: '신용카드 매출전표', "
                            "'승인번호 12345678')를 그대로 옮기세요. 이미지에 없는 글자는 "
                            "절대 만들지 말고 null로 두세요."
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
        config={"run_name": "backend_receipt_vision"},
    )
    return ReceiptExtractionGeneration.model_validate(result)


async def extract_receipt_from_ocr(
    llm: BaseChatModel,
    *,
    ocr_text: str,
) -> ReceiptExtractionGeneration:
    """OCR이 읽은 글자만 보고 영수증 필드를 정리한다(이미지는 보지 않는다)."""
    structured_model = llm.with_structured_output(ReceiptExtractionGeneration)
    prompt = ChatPromptTemplate.from_messages(
        [
            HumanMessage(
                content=(
                    "아래는 영수증 이미지를 OCR로 읽은 결과입니다. 줄 번호와 줄별 신뢰도"
                    "(%)가 붙어 있고 오인식이 섞여 있을 수 있습니다. 이 글자만 근거로 거래일, "
                    "상호, 총액, 품목을 정리하세요. 확인할 수 없는 값은 null 또는 빈 배열로 "
                    "반환하고 값을 추정하지 마세요. 숫자는 OCR 결과를 우선하되, 같은 글자가 "
                    "다른 줄에서 다르게 읽혔거나 문맥상 명백한 오인식(예: 'O'와 '0')만 바로잡으세요. "
                    "총액은 합계·결제금액처럼 최종 금액이 적힌 줄을 기준으로 하세요. "
                    "items에는 상품·서비스 이름으로 뜻이 읽히는 줄만 넣으세요. 신뢰도가 낮고 "
                    "뜻을 알 수 없게 깨진 글자(예: 'Be: A4SAl')는 품목으로 추측해 고치거나 "
                    "넣지 말고 버리세요. "
                    + _RECEIPT_CATEGORY_RULES
                    + "\n\n"
                    + _RECEIPT_PROOF_RULES
                    + "\n\n또한 값을 읽어낸 근거를 남기세요. date_text, vendor_text, "
                    "amount_text에는 각각 거래일·상호·총액이 적힌 OCR 줄의 글자를 그대로 "
                    "옮기고(줄 번호와 신뢰도는 빼세요), proof_evidence에는 proof_type을 그렇게 "
                    "판단한 근거 문구를 OCR 글자 그대로 옮기세요. OCR 결과에 없는 글자는 "
                    "절대 만들지 말고 null로 두세요.\n\n[OCR 결과]\n" + ocr_text
                )
            )
        ]
    )
    result = await (prompt | structured_model).ainvoke(
        {},
        config={"run_name": "backend_receipt_ocr_llm"},
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
