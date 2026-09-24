"""Backend 전용 구조화 작업을 수행하는 LLM chain 모음."""

from __future__ import annotations

import json
import re
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

    지원사업 공고 양식을 받았으면 그 항목 구성을, 받지 못했으면 기본 양식 13개 입력 칸을 따른다.
    """

    sections: list[BusinessPlanSectionGeneration]
    summary: str


BUSINESS_PLAN_ANALYSIS_MARKER = "__FIELD_ANALYSIS_V1__"
BUSINESS_PLAN_CONTEXT_MARKER = "__FIELD_CONTEXT_V1__\n"
BUSINESS_PLAN_EDITS_MARKER = "__USER_EDITS_V1__\n"


class BusinessPlanFieldAssessment(_GeneratedOutput):
    field_id: str
    section_id: str = ""
    type: Literal["text", "multiline_text", "list", "table", "image", "metadata", "non_input"]
    columns: list[str] = Field(default_factory=list)
    instruction: str
    required_information: list[str]
    status: Literal["ready", "partial", "missing", "not_applicable", "unsupported", "non_input"]
    missing_fields: list[str]
    missing_reason: str
    mapped_information: list[str]


class BusinessPlanFieldAnalysis(_GeneratedOutput):
    fields: list[BusinessPlanFieldAssessment]


def _normalize_plan_table(content: str, label: str) -> str:
    if not content.strip():
        return ""
    match = re.search(r"\[표: ([^\]]+)\]", label)
    if not match:
        return content
    if content.strip().startswith("정보 부족"):
        return ""
    columns = [column.strip() for column in match.group(1).split("|")]
    try:
        data = json.loads(content)
        rows = data["rows"]
    except (ValueError, TypeError, KeyError):
        rows = []
        for line in content.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if cells == columns or not any(cells):
                continue
            if len(cells) != len(columns):
                raise ValueError(f"표 열 형식이 맞지 않습니다: {label}")
            rows.append(dict(zip(columns, cells)))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"표 행 형식이 맞지 않습니다: {label}")
    normalized = [{column: str(row[column]).strip()
                   if row.get(column) is not None and str(row[column]).strip() else None
                   for column in columns} for row in rows]
    return json.dumps({"rows": normalized}, ensure_ascii=False)


def _clear_unprovided_table_cells(content: str, field: dict) -> str:
    if not content:
        return content
    data = json.loads(content)
    unanswered = [item for item in field.get("missing", [])
                  if not field.get("answers", {}).get(item)]
    source = " ".join([*field.get("mapped", []),
                       *(str(value) for value in field.get("answers", {}).values() if value)])
    source_numbers = set(re.findall(r"\d+(?:[.,]\d+)*", source))
    has_period = bool(re.search(r"20\d{2}|\d{1,2}월|분기|상반기|하반기|\d+개월|\d+주", source))
    for row in data["rows"]:
        for column in row:
            normalized_column = re.sub(r"\W", "", column)
            if any(normalized_column in re.sub(r"\W", "", item)
                   or re.sub(r"\W", "", item) in normalized_column
                   for item in unanswered):
                row[column] = None
                continue
            numbers = re.findall(r"\d+(?:[.,]\d+)*", str(row[column] or ""))
            if any(number not in source_numbers for number in numbers) or (
                re.search(r"기간|일정|시기|연월", column) and row[column] and not has_period
            ):
                row[column] = None
    return json.dumps(data, ensure_ascii=False)


class BusinessPlanRefinement(_GeneratedOutput):
    businessName: str = Field(max_length=100)
    tagline: str = Field(max_length=200)
    startupStatus: str = Field(max_length=100)
    industry: str = Field(max_length=100)
    businessRegion: str = Field(max_length=100)
    businessType: str = Field(max_length=100)
    targetCustomer: str = Field(max_length=500)
    problem: str = Field(max_length=1000)
    solution: str = Field(max_length=1000)
    coreFeatures: str = Field(max_length=1000)
    differentiator: str = Field(max_length=500)
    revenueModel: str = Field(max_length=500)
    team: str = Field(max_length=500)
    extraNotes: str = Field(max_length=1000)


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


BUSINESS_PLAN_DEFAULT_FIELDS = [
    ("applicationStatus", "신청현황", "창업 상태와 사업 신청에 필요한 현재 현황. 공고를 선택한 경우에만 공고명 포함"),
    ("generalStatus", "일반현황", "사업/아이템명, 업종, 사업 지역, 사업 형태와 팀 구성"),
    ("itemOverview", "창업아이템 개요(요약)", "아이템 소개, 목표 고객, 핵심 기능, 차별점과 수익 방식 요약"),
    ("motivation", "1-1. 창업아이템의 개발 동기 / 개발 추진경과(이력)", "고객 문제를 발견한 배경과 지금까지 실제로 진행한 내용"),
    ("purpose", "1-2. 창업아이템의 개발 목적", "해결하려는 문제와 제품·서비스의 개발 목적"),
    ("targetMarket", "1-3. 창업아이템의 목표시장 분석", "목표 고객과 시장 특성, 경쟁 상황"),
    ("developmentPlan", "2-1. 창업아이템의 개발 방안 / 진행(준비) 정도", "핵심 기능, 개발 방법, 현재 준비 정도와 최종 산출물"),
    ("differentiation", "2-2. 창업아이템의 차별화 방안", "경쟁 제품·서비스와 비교한 차별점과 경쟁력 확보 방안"),
    ("commercialization", "3-1. 창업아이템의 사업화 방안", "수익 방식과 생산·출시·홍보·판매 방안"),
    ("schedule", "3-2. 사업 추진 일정", "실제로 제공된 일정과 단계별 목표"),
    ("funding", "3-3. 자금소요 및 조달계획", "실제로 제공된 소요 자금, 정부지원금 사용 및 조달계획"),
    ("representative", "4-1. 대표자 현황 및 보유역량", "대표자의 실제 경력과 아이템 구현·판매 역량"),
    ("teamCapability", "4-2. 팀 현황 및 보유역량", "팀원과 역할, 보유역량 및 협력 계획"),
]

BUSINESS_PLAN_DEFAULT_SECTIONS_INSTRUCTION = (
    "기본 사업계획서 양식의 입력 칸 13개를 아래 순서와 key·label로 정확히 한 번씩 작성하세요. "
    "사용자가 제공하지 않은 일정·자금·경력·실적은 추측하지 말고 content를 '정보 부족'으로 "
    "작성하세요:\n"
    + "\n".join(
        f'{index}. key="{key}", label="{label}" — {description}'
        for index, (key, label, description) in enumerate(BUSINESS_PLAN_DEFAULT_FIELDS, 1)
    )
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
            """
제출 대상의 공고 또는 양식에 맞춰 사업계획서 초안을 작성하고,
사용자가 제시한 사업 아이디어를 사업계획서에 적합한 수준으로 구체화하는 보조 도구다.

[핵심 원칙]
사용자가 제공한 사실과 사업 방향을 가장 우선적인 근거로 사용하세요.
단순히 사용자의 문장을 길게 바꾸는 데 그치지 말고,
사용자가 제시한 아이디어의 의도와 방향을 유지하면서
목적, 작동 방식, 고객 가치, 사업화 방식, 수익 구조 등의 관계를
논리적으로 연결하여 구체화하세요.

[사실 정보]
매출액, 투자 유치액, 이용자 수, 계약 건수, 개발 완료 여부,
사업 수행 실적, 대표자 경력 등 사실 확인이 필요한 정보는
사용자가 제공하지 않았다면 절대 만들어 내지 마세요.

해당 항목에 필요한 사실이 없다면 아래 sections 항목 구성의 빈칸 처리 규칙을 따르세요.

[아이디어 구체화]
사용자가 제공한 아이디어로부터 직접 설명할 수 있는 목적, 운영 방식,
문제 해결 과정, 고객 가치, 수익 구조 등은 적극적으로 구체화하세요.

[새로운 아이디어 제안]
사용자가 명시하지 않은 새로운 기능, 전략 또는 수익모델을
기존 아이디어의 일부인 것처럼 단정해서는 안 됩니다.

사업 내용을 보완하는 데 도움이 되는 추가 아이디어가 있다면
'고려할 수 있습니다', '활용할 수 있습니다',
'확장할 수 있습니다'와 같이 제안의 형태로만 작성하세요.

sections 항목 구성:
{sections_instruction}

summary는 sections 전체 내용을 3문장으로 압축한 요약입니다.
            """,
        ),
        (
            "human",
            "사업/아이템명: {business_name}\n창업 상태: {startup_status}\n업종: {industry}\n"
            "사업 지역: {business_region}\n사업 형태: {business_type}\n팀 구성: {team_input}\n"
            "목표 고객: {target_customer}\n"
            "핵심 문제: {problem_input}\n해결 방안: {solution_input}\n핵심 기능: {core_features}\n"
            "차별점: {differentiator}\n수익 방식: {revenue_model}\n"
            "신청하려는 지원사업(선택): {target_program}\n"
            "추가로 참고할 내용(선택): {extra_notes}\n공고 평가 기준(있는 경우): {announcement_criteria}\n"
            "사용자가 평가 후 보완한 초안 항목(있는 경우):\n{reviewed_sections_text}",
        ),
    ]
)


BUSINESS_PLAN_FIELD_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """사업계획서 양식의 실제 작성 칸을 사용자 정보와 비교한다.
각 입력 칸을 주어진 field_id 순서대로 정확히 한 번씩 분석한다.
제목의 [표: ...]는 실제 표의 열이며, [행: ...]은 양식에 고정된 행 이름이다.
type은 text, multiline_text, list, table, image, metadata, non_input 중 하나다.
required_information은 그 칸을 실제로 작성하는 데 필요한 구체 정보다.
mapped_information에는 사용자 입력에서 해당 칸에 직접 관련되는 사실만 넣는다.
의미와 목적을 판단하여 매핑하고, 같은 문장을 여러 칸에 기계적으로 복사하지 않는다.
날짜, 기간, 금액, 실적, 경력, 해외 계획은 명시된 사실이 없으면 없다고 판단한다.
ready는 필요한 사실이 충분한 경우, partial은 일부 사실만 있는 경우,
missing은 핵심 사실이 전혀 없는 경우, unsupported는 입력 위치 또는 형식을
안전하게 채울 수 없는 경우, non_input은 작성 칸이 아닌 경우다.
사용자가 해당 계획이나 실적이 없다고 명시했다면 not_applicable이다.
missing_fields는 실제로 부족한 세부 정보를 적고, missing_reason은 그 이유를 짧게 적는다.
표는 각 열의 의미와 고정 행을 따로 판단한다. 예시 문구를 사용자 사실로 보지 않는다."""),
    ("human", "양식 입력 칸:\n{field_list}\n\n사용자 정보:\n{user_information}"),
])


async def analyze_business_plan_fields(
    llm: BaseChatModel, *, template_fields: list[str], user_information: dict[str, str]
) -> BusinessPlanFieldAnalysis:
    chain = BUSINESS_PLAN_FIELD_ANALYSIS_PROMPT | llm.with_structured_output(BusinessPlanFieldAnalysis)
    result = BusinessPlanFieldAnalysis.model_validate(await chain.ainvoke({
        "field_list": "\n".join(f"section_{index}: {name}"
                               for index, name in enumerate(template_fields, 1)),
        "user_information": "\n".join(f"{key}: {value or '(입력 없음)'}"
                                       for key, value in user_information.items()),
    }, config={"run_name": "backend_business_plan_field_analysis"}))
    by_id = {field.field_id: field for field in result.fields}
    normalized_fields = []
    for index, name in enumerate(template_fields, 1):
        field_id = f"section_{index}"
        field = by_id.get(field_id) or BusinessPlanFieldAssessment(
            field_id=field_id,
            type="table" if "[표:" in name else "multiline_text",
            instruction=name,
            required_information=[], status="unsupported", missing_fields=[],
            missing_reason="입력 영역의 요구 정보를 안정적으로 분석하지 못했습니다.",
            mapped_information=[],
        )
        columns_match = re.search(r"\[표: ([^\]]+)\]", name)
        section_match = re.match(r"\s*(\d+(?:[-.]\d+)*)", name)
        columns = [part.strip() for part in columns_match.group(1).split("|")] if columns_match else []
        image_label = name.split(" [", 1)[0].strip()
        field_type = ("table" if columns else "metadata" if "[유형: metadata]" in name
                      else "image" if "[유형: image]" in name or re.search(r"(?:이미지|사진|도면|로고|image|photo|logo)(?:\s*\d+)?$", image_label, re.I)
                      else field.type)
        status = "missing" if field_type == "image" else field.status
        metadata_label = name.split(" [", 1)[0].strip()
        known_metadata = {"창업아이템명": user_information.get("사업명", ""),
                          "신청자 성명": user_information.get("신청자 성명", "")}
        if field_type == "metadata" and metadata_label in known_metadata:
            known_value = known_metadata[metadata_label].strip()
            status = "ready" if known_value else "missing"
            field = field.model_copy(update={
                "required_information": [metadata_label],
                "missing_fields": [] if known_value else [metadata_label],
                "missing_reason": "" if known_value else f"{metadata_label} 정보가 제공되지 않았습니다.",
                "mapped_information": [known_value] if known_value else [],
            })
        elif field_type == "metadata" and metadata_label in {
            "생년월일", "성별", "직업", "기업명", "기술분야"
        }:
            status = "missing"
            field = field.model_copy(update={
                "required_information": [metadata_label],
                "missing_fields": [metadata_label],
                "missing_reason": f"프로필에 {metadata_label} 정보가 없습니다.",
                "mapped_information": [],
            })
        elif field_type == "metadata" and status in {"unsupported", "non_input", "missing"}:
            status = "missing"
            field = field.model_copy(update={
                "required_information": field.required_information or [metadata_label],
                "missing_fields": field.missing_fields or [metadata_label],
                "missing_reason": field.missing_reason or f"{metadata_label} 정보가 제공되지 않았습니다.",
            })
        normalized_fields.append(field.model_copy(update={
            "section_id": section_match.group(1) if section_match else "",
            "type": field_type,
            "columns": columns,
            "status": status,
            "required_information": ["이미지 파일"] if field_type == "image" else field.required_information,
            "missing_fields": ["이미지 파일"] if field_type == "image" else field.missing_fields,
            "missing_reason": "이미지 파일을 첨부해 주세요." if field_type == "image" else field.missing_reason,
        }))
    return BusinessPlanFieldAnalysis(fields=normalized_fields)


async def generate_business_plan(
    llm: BaseChatModel,
    *,
    business_name: str,
    applicant_name: str = "",
    tagline: str,
    startup_status: str,
    industry: str,
    business_region: str,
    business_type: str,
    target_customer: str,
    problem_input: str,
    solution_input: str,
    core_features: str,
    differentiator: str,
    revenue_model: str,
    team_input: str,
    target_program: str,
    extra_notes: str,
    template_text: str = "",
    template_fields: list[str] | None = None,
    reviewed_sections: list[dict] | None = None,
    announcement_criteria: str = "",
) -> BusinessPlanGeneration:
    """사용자가 입력한 사업 정보로 사업계획서 초안을 생성한다.

    template_text가 있으면 그 지원사업 공고 양식의 항목 구성을 따르고, 없으면 기본
    양식의 신청·일반현황, 개요와 1-1부터 4-2까지 13개 입력 칸을 채운다.
    """
    has_template = bool(template_fields or (template_text.strip()
                                   and not template_text.startswith(BUSINESS_PLAN_EDITS_MARKER)))
    context = {}
    if template_text.startswith(BUSINESS_PLAN_CONTEXT_MARKER):
        parsed_context = json.loads(template_text[len(BUSINESS_PLAN_CONTEXT_MARKER):])
        context = {"fields": parsed_context} if isinstance(parsed_context, list) else parsed_context
    elif template_text.startswith(BUSINESS_PLAN_EDITS_MARKER):
        context = {"editedKeys": json.loads(template_text[len(BUSINESS_PLAN_EDITS_MARKER):])}
    field_context = {item["id"]: item for item in context.get("fields", [])}
    edited_keys = set(context.get("editedKeys", []))
    if reviewed_sections:
        sections_instruction = (
            "보완한 초안의 항목을 같은 key·label과 순서로 각각 한 번씩 작성하세요:\n"
            + "\n".join(f"{index}. key={section['key']}, label={section['label']}"
                        for index, section in enumerate(reviewed_sections, 1))
        )
    elif template_fields:
        sections_instruction = (
            "첨부 양식의 입력 항목을 같은 순서·이름으로 각각 한 번씩 작성하세요. "
            "key는 section_1, section_2처럼 순서대로 지정하세요:\n"
            + "\n".join(f"{index}. {name}" for index, name in enumerate(template_fields, 1))
        )
    elif template_text.strip():
        sections_instruction = BUSINESS_PLAN_TEMPLATE_SECTIONS_INSTRUCTION.format(
            template_text=template_text.strip()
        )
    else:
        sections_instruction = BUSINESS_PLAN_DEFAULT_SECTIONS_INSTRUCTION
    if template_fields and field_context:
        sections_instruction += (
            "\n[입력 칸별 분석 및 사용자 보완 정보]\n"
            + json.dumps(context["fields"], ensure_ascii=False)
            + "\n각 칸의 instruction, required_information, mapped와 사용자 보완 답변을 따르세요. "
            "표의 content는 반드시 JSON 문자열 {\"rows\":[{\"열 이름\":\"값\" 또는 null}]} 형식으로 쓰세요. "
            "명시되지 않은 날짜·기간·금액·경력·성과의 셀 값은 null로 두세요. "
            "고정 행 이름이 있으면 그 순서와 이름을 유지하세요. "
            "[글머리표: ...]가 있는 글 칸은 인쇄된 ○와 -의 순서에 맞춰 논점을 짧은 문장으로 줄바꿈해 작성하세요. "
            "필요한 문장이 적으면 글머리표를 모두 채우려고 반복하지 마세요. "
            "status가 not_applicable인 글 칸은 '해당 사항 없음', 표 칸은 빈 문자열로 두세요. "
            "status가 unsupported 또는 non_input인 칸은 빈 문자열로 두세요. "
            "image 칸은 첨부 파일을 문서 출력 때 따로 배치하므로 content를 빈 문자열로 두세요."
        )
    if reviewed_sections:
        sections_instruction += (
            "\n사용자가 직접 수정한 항목은 그 내용을 절대 삭제하거나 다른 사실로 바꾸지 마세요. "
            "그 외 항목은 문장을 다듬고 중복을 줄이되 새로운 사실·수치·실적을 만들지 마세요. "
            f"사용자 직접 수정 항목 key: {', '.join(sorted(edited_keys)) or '(없음)'}"
        )
    if has_template:
        sections_instruction += (
            "\n첨부 양식의 항목 제목이 요구하는 내용만 해당 content에 작성하세요. "
            "기본 사업계획서의 13개 항목이나 PSST 구성을 적용하거나 다른 항목의 내용을 "
            "우겨 넣지 마세요. 같은 사용자 사실을 여러 칸에 같은 문장으로 반복하지 말고, "
            "시장진입 전략에는 고객 확보 방법을, 수익모델에는 과금 구조를 구분해 작성하세요. "
            "양식의 예시·임시 답안은 사업 사실로 사용하지 마세요. "
            "사용자 입력 또는 보완한 항목에서 이 항목에 쓸 근거를 찾을 수 없으면 "
            "content를 빈 문자열로 두세요. '정보 부족' 같은 대체 문구도 쓰지 마세요."
        )
    elif reviewed_sections:
        sections_instruction += "\n필요한 정보가 없으면 content를 '정보 부족'으로 적으세요."
    chain = BUSINESS_PLAN_PROMPT | llm.with_structured_output(BusinessPlanGeneration)
    result = BusinessPlanGeneration.model_validate(
        await chain.ainvoke(
            {
                "sections_instruction": sections_instruction,
                "business_name": business_name or "(입력 없음)",
                "tagline": tagline or "(입력 없음)",
                "startup_status": startup_status or "(입력 없음)",
                "industry": industry or "(입력 없음)",
                "business_region": business_region or "(입력 없음)",
                "business_type": business_type or "(입력 없음)",
                "target_customer": target_customer or "(입력 없음)",
                "problem_input": problem_input or "(입력 없음)",
                "solution_input": solution_input or "(입력 없음)",
                "core_features": core_features or "(입력 없음)",
                "differentiator": differentiator or "(입력 없음)",
                "revenue_model": revenue_model or "(입력 없음)",
                "team_input": team_input or "(입력 없음)",
                "target_program": target_program or "(입력 없음)",
                "extra_notes": extra_notes or "(없음)",
                "announcement_criteria": announcement_criteria or "(없음)",
                "reviewed_sections_text": "\n\n".join(
                    f"[{section['label']}]\n{section['content']}"
                    for section in (reviewed_sections or [])
                ) or "(없음)",
            },
            config={"run_name": "backend_business_plan"},
        )
    )
    by_key = {section.key.strip(): section for section in result.sections}
    by_label = {section.label.strip(): section for section in result.sections}
    if reviewed_sections:
        expected_fields = [(section["key"], section["label"]) for section in reviewed_sections]
    elif template_fields:
        expected_fields = [(f"section_{index}", name) for index, name in enumerate(template_fields, 1)]
    elif template_text.strip():
        expected_fields = None
    else:
        expected_fields = [(key, label) for key, label, _ in BUSINESS_PLAN_DEFAULT_FIELDS]
    missing_content = "" if has_template else "정보 부족"
    if expected_fields is not None:
        sections = []
        for key, label in expected_fields:
            matched_section = by_key.get(key) or by_label.get(label)
            sections.append(BusinessPlanSectionGeneration(
                key=key,
                label=label,
                content=matched_section.content if matched_section else missing_content,
            ))
    else:
        sections = result.sections
    if field_context:
        sections = [section.model_copy(update={"content": ""})
                    if field_context.get(section.key, {}).get("status") in {"unsupported", "non_input"}
                    or field_context.get(section.key, {}).get("type") == "image"
                    or (field_context.get(section.key, {}).get("status") == "missing"
                        and not any(field_context[section.key].get("answers", {}).values())
                        and not field_context[section.key].get("mapped"))
                    else section for section in sections]
        sections = [section.model_copy(update={"content": (
            "" if field_context.get(section.key, {}).get("type") in {"table", "image"} else "해당 사항 없음"
        )}) if field_context.get(section.key, {}).get("status") == "not_applicable"
            else section for section in sections]
    if reviewed_sections and edited_keys:
        reviewed_by_key = {section["key"]: section["content"] for section in reviewed_sections}
        sections = [section.model_copy(update={"content": reviewed_by_key[section.key]})
                    if section.key in edited_keys and section.key in reviewed_by_key
                    else section for section in sections]
    known_metadata = {"창업아이템명": business_name.strip(),
                      "신청자 성명": applicant_name.strip()}
    personal_metadata = {"생년월일", "성별", "직업", "기업명", "기술분야"}
    normalized_metadata = []
    for section in sections:
        if "[유형: metadata]" not in section.label or section.key in edited_keys:
            normalized_metadata.append(section)
            continue
        label = section.label.split(" [", 1)[0].strip()
        answers = field_context.get(section.key, {}).get("answers", {})
        supplied = next((str(value).strip() for value in answers.values() if str(value).strip()), "")
        if label in known_metadata or label in personal_metadata:
            section = section.model_copy(update={
                "content": supplied or known_metadata.get(label, "")
            })
        normalized_metadata.append(section)
    sections = normalized_metadata
    sections = [section.model_copy(update={"content": _normalize_plan_table(section.content, section.label)})
                for section in sections]
    sections = [section.model_copy(update={
        "content": _clear_unprovided_table_cells(section.content, field_context[section.key])
    }) if section.key in field_context and section.key not in edited_keys
        and "[표:" in section.label else section for section in sections]
    result = result.model_copy(update={"sections": sections})
    return result.model_copy(
        update={
            "sections": [
                section.model_copy(
                    update={
                        "content": (
                            "" if (has_template or section.key in edited_keys) and (
                                not section.content.strip()
                                or section.content.strip().startswith("정보 부족")
                                or any(
                                    reviewed.get("key") == section.key and not reviewed.get("content", "").strip()
                                    for reviewed in (reviewed_sections or [])
                                )
                            ) else validate_generated_text(
                                section.content, field_name=f"section:{section.key}"
                            )
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
            "사업계획서 검토자로서 아래 사업계획서 초안을 항목별로 "
            "평가하세요. 이것은 예비진단이며 실제 합격을 보장하지 않는다는 전제로, 초안에 "
            "실제로 쓰인 내용만 근거로 채점하세요. 빈 항목이나 '정보 부족', '[직접 채워 주세요: ...]' "
            "항목은 아직 채워지지 않은 것으로 보고 감점 사유로 다루세요. "
            "단, [유형: image]로 표시된 칸은 이미지가 별도로 첨부되므로 빈칸이어도 감점하지 마세요. "
            "점수는 내용의 구체성·논리적 연결·실현 가능성을 기준으로 0~100점, 5점 단위 권장. sections에는 "
            "아래에 주어진 항목을 모두, 주어진 순서 그대로, 같은 key·label로 반환하세요. 각 "
            "항목의 strengths(잘된 점)와 improvements(보완할 점)는 1~2문장, 존댓말로 구체적으로 "
            "쓰세요. overall_comment는 전체를 한두 문장으로 평가하세요. "
            "공고 기준이 있으면 양식 기준과 함께 적용하고, 공고가 없으면 양식 기준을 적용하세요. "
            "공고가 선택되지 않았다는 사실만으로 감점하지 마세요.\n"
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
