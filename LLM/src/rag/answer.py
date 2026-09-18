"""Policy·Notice·Tax 상태를 공통 사용자 응답으로 변환한다."""

import json
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ConfigDict, Field

from src.rag.history import compact_conversation_history


AnswerStatus = Literal[
    "success",
    "need_more_info",
    "insufficient_evidence",
    "no_result",
    "integration_unavailable",
    "error",
]


class UnifiedAnswerResult(BaseModel):
    """Graph 최종 응답의 최소 Structured Output."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    status: AnswerStatus
    cited_source_numbers: list[int] = Field(default_factory=list)


ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "주어진 route Context에만 근거해 한국어로 직접 답하세요. 검색, 계산, "
            "법령 참조 추적을 새로 수행하지 마세요. Context에 없는 정책·공고·세법 "
            "내용을 만들지 마세요. route Context 문서의 citation_number만 "
            "cited_source_numbers에 기록하세요. source_id·문서 ID·조문 번호는 "
            "인용 번호가 아닙니다. 출처 번호는 cited_source_numbers에만 기록하고 "
            "answer 본문에는 [1], [2] 같은 각주 번호를 쓰지 마세요. "
            "최근 대화는 후속 질문의 의미와 표현을 잇는 문맥일 뿐 증거가 아닙니다. "
            "과거 assistant 답변만으로 법령·정책·금액을 확정하거나 출처로 인용하지 "
            "마세요. 현재 route Context와 deterministic 계산 결과만 근거로 사용하세요. "
            "계산 가정(calculation_assumptions)이 있으면 계산값과 함께 반드시 밝히고, "
            "사용자가 실제 값을 알려주면 다시 계산할 수 있다고 안내하세요. "
            "세금 계산이 완료된 경우 금액과 가정 안내는 시스템이 결정적으로 붙입니다. "
            "answer에는 계산 근거 설명만 쓰고 금액·숫자·가정값을 반복하거나 새로 만들지 마세요. "
            "세금의 일반 법적 기준 설명(tax_general_explanation=true)은 확인된 법령으로 "
            "뒷받침되는 일반 원칙부터 직접 설명하고 인용한 문서 번호는 "
            "cited_source_numbers에 기록하세요. 개인별 적용 "
            "여부나 확정 세액은 단정하지 마세요. 사용자 정보 부족을 이유로 일반 원칙의 "
            "답변을 생략하거나 여러 세부정보를 연달아 요구하지 마세요. "
            "질문에 먼저 직접 답하고 확인된 기준과 확인이 필요한 부분을 정중하고 "
            "자연스러운 문단으로 간결하게 설명하세요. '결론:', '적용 조건:', "
            "'주의사항:' 같은 기계적인 제목을 붙이지 마세요. "
            "status가 insufficient_evidence이고 인용 가능한 문서가 있으면 "
            "확인된 내용과 확정할 수 없는 이유를 구분해 설명하세요. "
            "대상·자격 여부를 묻고 인용 가능한 일반 기준이 있으면, 확인된 조건을 "
            "사용자가 대입해 볼 수 있도록 '이해를 돕기 위해 예를 들면'으로 시작하는 "
            "조건부 사례를 반드시 한 문단에 포함하세요. '모든 요건을 충족하면'처럼 "
            "조건을 되풀이하는 사례는 피하고, 문서에 나온 구체적인 조건을 쓰세요. "
            "그 가정이 실제 사용자 정보나 개인별 판정이 아님을 밝히세요. "
            "확인되지 않은 조건이 남아 있으면 해당 조건의 충족이나 최종 대상 여부를 "
            "단정하지 마세요. 부족한 정보 설명은 반복하지 말고 마지막 한 문장으로 "
            "줄여, 영향이 큰 항목 최대 두 개만 요청하세요. 대상·자격 질문의 답변은 "
            "확인된 기준과 조건부 예시를 중심으로 4~6문장 안에 마무리하세요. "
            "확인되지 않은 수치·자격·기간은 만들지 마세요. "
            "answer 본문에는 insufficient_evidence, route, Context 같은 개발 용어나 "
            "내부 상태 값을 쓰지 마세요. status 필드는 반드시 {status}로 반환하세요.",
        ),
        (
            "human",
            "route={route}\npersonalized={personalized}\n현재 질문: {query}\n"
            "독립 질문: {standalone_query}\n최근 대화: {conversation_history}\n"
            "사용자 Context: {user_context}\nroute Context:\n{route_context}",
        ),
    ]
)

TAX_ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        ANSWER_PROMPT.messages[0],
        (
            "system",
            "세금 답변은 질문에 대한 직접적인 안내 뒤에 필요한 적용 조건, "
            "계산 결과(있는 경우), 근거 법령과 핵심 이유를 자연스럽게 이어 설명하세요. "
            "같은 설명을 반복하거나 법령 원문을 길게 인용하지 마세요. "
            "서로 다른 법령·조항의 필수 근거는 빠뜨리지 마세요. "
            "사용자 정보가 부족해도 확인된 일반 기준을 먼저 설명하고, "
            "개인별 적용만 보류하세요. 감면 대상 질문에서는 확인된 연령·업종·"
            "최초 창업·지역 등의 실제 법령 조건 중 답변 근거에 있는 조건을 골라 "
            "'이 조건이라면 감면 대상에 해당할 수 있습니다'와 같이 적용 모습을 "
            "보여주는 예시를 답변 앞부분에 반드시 쓰세요. '법령상 모든 요건을 "
            "충족한다면'처럼 사용자가 판단할 수 없는 포괄적 가정은 쓰지 마세요. "
            "확정이 어렵다는 말은 예시 뒤에 짧게 덧붙이세요. 예시의 조건을 "
            "사용자 사실로 말하지 말고, "
            "근거에 없는 자격·감면율·기간을 덧붙이지 마세요. 문서에 일부 조건만 "
            "있다면 해당 조건을 충족하는 사례까지만 설명하고 최종 대상 여부는 "
            "다른 조건 확인이 필요하다고 밝히세요. 마지막에는 route Context의 "
            "missing_user_context에 적힌 항목 중 앞의 최대 두 개만 한 문장으로 "
            "요청하고, 목록에 없는 추가 정보를 새로 요구하지 마세요. "
            "evidence의 duplicate_of는 같은 조항의 앞선 출처 번호이며 중복 원문을 생략한 표시입니다.",
        ),
        ANSWER_PROMPT.messages[1],
    ]
)


async def generate_unified_answer(
    llm: BaseChatModel,
    *,
    query: str,
    standalone_query: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    route: str,
    personalized: bool,
    user_context: dict[str, object] | None,
    route_context: dict[str, object],
    status: AnswerStatus,
    source_count: int,
) -> UnifiedAnswerResult:
    """route에 필요한 Context만 전달해 최종 Structured Output을 생성한다."""
    prompt = TAX_ANSWER_PROMPT if route == "tax" else ANSWER_PROMPT
    chain = prompt | llm.with_structured_output(UnifiedAnswerResult)
    result = UnifiedAnswerResult.model_validate(
        await chain.ainvoke(
            {
                "query": query,
                "standalone_query": standalone_query or query,
                "conversation_history": json.dumps(
                    compact_conversation_history(conversation_history or []),
                    ensure_ascii=False,
                ),
                "route": route,
                "personalized": personalized,
                "user_context": json.dumps(user_context, ensure_ascii=False),
                "route_context": json.dumps(route_context, ensure_ascii=False),
                "status": status,
            },
            config={"run_name": "langgraph_unified_answer"},
        )
    )
    if result.status != status:
        raise ValueError("Unified answer changed the deterministic status")
    invalid_numbers = [
        number
        for number in result.cited_source_numbers
        if number < 1 or number > source_count
    ]
    if invalid_numbers:
        raise ValueError("Unified answer cited an unavailable source")
    if source_count and not result.cited_source_numbers:
        raise ValueError("Unified answer must cite at least one available source")
    return result.model_copy(
        update={"cited_source_numbers": list(dict.fromkeys(result.cited_source_numbers))}
    )


def fallback_answer(
    status: AnswerStatus,
    *,
    missing_user_context: list[str] | None = None,
) -> UnifiedAnswerResult:
    """근거가 없거나 integration이 없을 때 LLM 호출 없이 안전하게 응답한다."""
    messages: dict[AnswerStatus, str] = {
        "success": "확인된 근거를 바탕으로 답변했습니다.",
        "need_more_info": "정확한 판단을 위해 추가 정보가 필요합니다.",
        "insufficient_evidence": "현재 확인된 근거만으로는 확정하기 어렵습니다.",
        "no_result": "현재 조건에 맞는 결과를 찾지 못했습니다.",
        "integration_unavailable": "현재 실제 데이터를 조회하거나 계산할 수 없습니다.",
        "error": "요청을 처리하는 중 오류가 발생했습니다.",
    }
    answer = messages[status]
    if status == "need_more_info" and missing_user_context:
        answer = "정확한 판단을 위해 다음 정보가 필요합니다: " + ", ".join(
            missing_user_context
        )
    return UnifiedAnswerResult(answer=answer, status=status)
