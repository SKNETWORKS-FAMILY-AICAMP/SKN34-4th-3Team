from langchain_core.language_models.chat_models import BaseChatModel
from langsmith import traceable

from src.data.contracts import UserProfile
from src.rag.contracts import (
    EligibilityDecision,
    GeneratedGroundedAnswer,
    GeneratedPolicyDiscovery,
    GeneratedPolicyItem,
)
from src.rag.context_builder import PromptContext
from src.rag.prompts import (
    DECISION_EXPLANATION_PROMPT_VERSION,
    POLICY_DISCOVERY_PROMPT,
    POLICY_DISCOVERY_PROMPT_VERSION,
    RAG_PROMPT,
    format_decision_context,
    format_user_context,
)


MAX_POLICY_ITEMS = 3
MAX_POLICY_LIST_ITEMS = 2
MAX_LIMITATIONS = 1


@traceable(name="generate_answer", run_type="chain")
async def generate_answer(
    llm: BaseChatModel,
    *,
    question: str,
    prompt_context: PromptContext,
    decision: EligibilityDecision | None,
) -> GeneratedGroundedAnswer:
    """특정 정책 근거와 Backend 판정을 이용해 답변을 생성한다.

    Args:
        llm: 답변 생성에 사용할 LangChain 채팅 모델.
        question: 사용자가 입력한 특정 정책 질문.
        prompt_context: 길이와 정책별 개수 제한을 적용한 검색 근거 문맥.
        decision: Backend가 확정한 선택적 자격 판정 결과.

    Returns:
        답변, 제한사항과 참조한 출처 번호를 담은 구조화 출력.

    Notes:
        `ainvoke()`에서 실제 LLM API가 호출된다.
    """
    structured_chat_model = llm.with_structured_output(GeneratedGroundedAnswer)
    grounded_answer_chain = RAG_PROMPT | structured_chat_model
    generated_output = await grounded_answer_chain.ainvoke(
        {
            "question": question,
            "document_context": prompt_context.context_text,
            "decision_context": format_decision_context(decision),
        },
        config={
            "run_name": "grounded_rag_generation",
            "tags": ["rag", "grounded-answer"],
            "metadata": {
                "prompt_version": DECISION_EXPLANATION_PROMPT_VERSION,
                "policy_id": (
                    prompt_context.selected_chunks[0]["policy_id"]
                    if prompt_context.selected_chunks
                    else None
                ),
                "source_count": len(prompt_context.selected_chunks),
            },
        },
    )
    return GeneratedGroundedAnswer.model_validate(generated_output)


@traceable(name="generate_policy_summary", run_type="chain")
async def generate_policy_summary(
    llm: BaseChatModel,
    *,
    question: str,
    user: UserProfile,
    prompt_context: PromptContext,
) -> GeneratedPolicyDiscovery:
    """사용자 프로필과 검색 근거를 이용해 관련 정책을 요약한다.

    Args:
        llm: 정책 요약에 사용할 LangChain 채팅 모델.
        question: 사용자가 입력한 정책 탐색 질문.
        user: 검색과 설명을 개인화할 사용자·사업자 정보.
        prompt_context: 정책 다양성과 길이 제한을 적용한 검색 근거 문맥.

    Returns:
        정책별 요약, 관련 이유, 확인사항과 출처 번호를 담은 구조화 출력.

    Notes:
        사용자 프로필은 관련성 설명에만 사용하며 자격 판정에는 사용하지 않는다.
        `ainvoke()`에서 실제 LLM API가 호출된다.
    """
    structured_chat_model = llm.with_structured_output(GeneratedPolicyDiscovery)
    policy_summary_chain = POLICY_DISCOVERY_PROMPT | structured_chat_model
    generated_output = await policy_summary_chain.ainvoke(
        {
            "question": question,
            "user_context": format_user_context(user),
            "document_context": prompt_context.context_text,
        },
        config={
            "run_name": "personalized_policy_summary",
            "tags": ["rag", "policy-discovery", "personalized"],
            "metadata": {
                "prompt_version": POLICY_DISCOVERY_PROMPT_VERSION,
                "source_count": len(prompt_context.selected_chunks),
                "policy_count": len(
                    {
                        chunk["policy_id"]
                        for chunk in prompt_context.selected_chunks
                    }
                ),
            },
        },
    )
    return GeneratedPolicyDiscovery.model_validate(generated_output)


def compact_grounded_answer(
    generated_answer: GeneratedGroundedAnswer,
) -> GeneratedGroundedAnswer:
    """특정 정책 답변의 부가 안내를 핵심 한 개로 제한한다.

    Args:
        generated_answer: LLM이 반환한 특정 정책 구조화 출력.

    Returns:
        답변과 출처는 유지하고 limitations만 한 개로 제한한 출력.
    """
    return generated_answer.model_copy(
        update={"limitations": generated_answer.limitations[:MAX_LIMITATIONS]}
    )


def compact_policy_discovery(
    generated_discovery: GeneratedPolicyDiscovery,
) -> GeneratedPolicyDiscovery:
    """정책 탐색 출력을 사용자에게 필요한 최대 분량으로 제한한다.

    Args:
        generated_discovery: LLM이 반환한 정책 탐색 구조화 출력.

    Returns:
        정책 3개, 정책별 목록 2개, 전체 안내 1개로 제한한 구조화 출력.
    """
    compacted_policies = [
        GeneratedPolicyItem(
            policy_id=generated_policy.policy_id,
            summary=generated_policy.summary,
            eligibility_requirements=generated_policy.eligibility_requirements,
            exclusion_conditions=generated_policy.exclusion_conditions,
            support_details=generated_policy.support_details,
            application_period=generated_policy.application_period,
            relevance_reasons=generated_policy.relevance_reasons[
                :MAX_POLICY_LIST_ITEMS
            ],
            requirements_to_verify=generated_policy.requirements_to_verify[
                :MAX_POLICY_LIST_ITEMS
            ],
            cited_source_numbers=generated_policy.cited_source_numbers,
        )
        for generated_policy in generated_discovery.policies[:MAX_POLICY_ITEMS]
    ]
    return generated_discovery.model_copy(
        update={
            "policies": compacted_policies,
            "limitations": generated_discovery.limitations[:MAX_LIMITATIONS],
        }
    )


def format_grounded_answer(generated_answer: GeneratedGroundedAnswer) -> str:
    """특정 정책 구조화 출력을 기존 API의 answer 문자열로 변환한다.

    Args:
        generated_answer: 검증이 완료된 특정 정책 구조화 출력.

    Returns:
        답변과 선택적 한계 안내를 결합한 사용자 표시 문자열.
    """
    grounded_answer = generated_answer.answer.strip()
    citation_markers = [
        f"[출처 {source_number}]"
        for source_number in dict.fromkeys(generated_answer.cited_source_numbers)
    ]
    missing_citation_markers = [
        citation_marker
        for citation_marker in citation_markers
        if citation_marker not in grounded_answer
    ]
    if missing_citation_markers:
        grounded_answer = f"{grounded_answer}\n{' '.join(missing_citation_markers)}"

    answer_sections = [grounded_answer]
    limitations = [
        item.strip() for item in generated_answer.limitations if item.strip()
    ]
    if limitations:
        answer_sections.append(
            "확인 사항:\n" + "\n".join(f"- {item}" for item in limitations)
        )
    return "\n\n".join(answer_sections)


def format_policy_discovery_answer(
    generated_discovery: GeneratedPolicyDiscovery,
    *,
    policy_titles: dict[int, str],
) -> str:
    """정책 탐색 구조화 출력을 기존 API의 answer 문자열로 변환한다.

    Args:
        generated_discovery: 검증이 완료된 정책 탐색 구조화 출력.
        policy_titles: Retriever 결과에서 가져온 policy_id별 실제 문서 제목.

    Returns:
        정책명, 자격, 지원 내용, 신청기간과 출처만 고정 순서로 결합한 문자열.
    """
    policy_count = len(generated_discovery.policies)
    answer_sections = [f"회원님과 관련이 높은 정책 {policy_count}개를 찾았습니다."]
    for policy_number, generated_policy in enumerate(
        generated_discovery.policies,
        start=1,
    ):
        policy_lines = [
            f"{policy_number}. {policy_titles[generated_policy.policy_id]}",
            _format_list_section("자격", generated_policy.eligibility_requirements),
            _format_list_section("지원 내용", generated_policy.support_details),
            _format_list_section(
                "신청기간",
                [generated_policy.application_period]
                if generated_policy.application_period
                else [],
            ),
            " ".join(
                f"[출처 {source_number}]"
                for source_number in dict.fromkeys(
                    generated_policy.cited_source_numbers
                )
            ),
        ]
        answer_sections.append("\n\n".join(policy_lines))

    return "\n\n".join(answer_sections)


def _format_list_section(section_title: str, values: list[str]) -> str:
    """정책 정보 목록을 고정 제목과 bullet 형식으로 변환한다.

    Args:
        section_title: 사용자에게 표시할 고정 섹션 제목.
        values: 공식 문서 또는 구조화 출력에서 가져온 항목 목록.

    Returns:
        빈 값이면 `확인 필요`, 값이 있으면 정리된 bullet 목록이 포함된 문자열.
    """
    normalized_values = [value.strip() for value in values if value and value.strip()]
    display_values = normalized_values or ["확인 필요"]
    return f"[{section_title}]\n" + "\n".join(
        f"- {display_value}" for display_value in display_values
    )
