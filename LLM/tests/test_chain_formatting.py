from src.rag.chain import (
    compact_grounded_answer,
    compact_policy_discovery,
    format_policy_discovery_answer,
)
from src.rag.contracts import (
    GeneratedGroundedAnswer,
    GeneratedPolicyDiscovery,
    GeneratedPolicyItem,
)


def make_policy(policy_id: int) -> GeneratedPolicyItem:
    """분량 제한 테스트용 정책 구조화 출력을 생성한다."""
    return GeneratedPolicyItem(
        policy_id=policy_id,
        summary=f"정책 {policy_id} 요약",
        eligibility_requirements=["만 18세 이상 만 34세 이하"],
        exclusion_conditions=["다른 정부 사업 참여자"],
        support_details=["사업화 자금 최대 1,000만 원"],
        application_period="2026.09.01 ~ 2026.09.30",
        relevance_reasons=["이유 1", "이유 2", "이유 3"],
        requirements_to_verify=["확인 1", "확인 2", "확인 3"],
        cited_source_numbers=[1],
    )


def test_policy_discovery_is_compacted_to_concise_limits() -> None:
    generated_discovery = GeneratedPolicyDiscovery(
        overview="관련 정책 안내",
        policies=[make_policy(policy_id) for policy_id in range(1, 5)],
        limitations=["안내 1", "안내 2"],
    )

    compacted_discovery = compact_policy_discovery(generated_discovery)

    assert len(compacted_discovery.policies) == 3
    assert all(
        len(policy.relevance_reasons) == 2
        for policy in compacted_discovery.policies
    )
    assert all(
        len(policy.requirements_to_verify) == 2
        for policy in compacted_discovery.policies
    )
    assert all(policy.eligibility_requirements for policy in compacted_discovery.policies)
    assert all(policy.exclusion_conditions for policy in compacted_discovery.policies)
    assert all(policy.support_details for policy in compacted_discovery.policies)
    assert all(policy.application_period for policy in compacted_discovery.policies)
    assert compacted_discovery.limitations == ["안내 1"]


def test_grounded_answer_keeps_only_one_limitation() -> None:
    generated_answer = GeneratedGroundedAnswer(
        answer="근거 답변",
        cited_source_numbers=[1],
        limitations=["확인 1", "확인 2"],
    )

    compacted_answer = compact_grounded_answer(generated_answer)

    assert compacted_answer.answer == "근거 답변"
    assert compacted_answer.limitations == ["확인 1"]


def test_single_policy_uses_fixed_section_order_and_structured_values() -> None:
    policy = GeneratedPolicyItem(
        policy_id=101,
        summary="formatter가 최종 출력에 사용하면 안 되는 자유 형식 요약",
        eligibility_requirements=["만 18세 이상", "만 34세 이하"],
        exclusion_conditions=["동일 기간 다른 전일제 사업 참여자", "허위 서류 제출자"],
        support_details=["사업화 자금 최대 1,000만 원"],
        application_period="2026.09.01 ~ 2026.09.30",
        relevance_reasons=["청년 창업자 대상", "사업 지역 일치"],
        requirements_to_verify=["업종 제한", "사업자등록일 기준"],
        cited_source_numbers=[1, 2],
    )
    generated_discovery = GeneratedPolicyDiscovery(
        overview="LLM이 생성한 정책 개수 문장",
        policies=[policy],
        limitations=["최종 자격은 별도 확인"],
    )

    formatted_answer = format_policy_discovery_answer(
        generated_discovery,
        policy_titles={101: "지역청년 초기창업 사업화지원 공고"},
    )

    expected_sections = [
        "회원님과 관련이 높은 정책 1개를 찾았습니다.",
        "1. 지역청년 초기창업 사업화지원 공고",
        "[자격]",
        "[지원 내용]",
        "[신청기간]",
        "[출처 1] [출처 2]",
    ]
    section_positions = [formatted_answer.index(section) for section in expected_sections]
    assert section_positions == sorted(section_positions)
    assert "- 만 18세 이상" in formatted_answer
    assert "- 사업화 자금 최대 1,000만 원" in formatted_answer
    assert "- 2026.09.01 ~ 2026.09.30" in formatted_answer
    assert "자유 형식 요약" not in formatted_answer
    assert "제한 사항" not in formatted_answer
    assert "회원님과 맞는 점" not in formatted_answer
    assert "확인할 사항" not in formatted_answer
    assert "안내 사항" not in formatted_answer
    assert "최종 자격은 별도 확인" not in formatted_answer
    assert "\n\n- 만 18세 이상" not in formatted_answer


def test_multiple_policy_count_uses_actual_compacted_policy_count() -> None:
    generated_discovery = GeneratedPolicyDiscovery(
        overview="정책 99개를 찾았습니다.",
        policies=[make_policy(101), make_policy(102), make_policy(103)],
        limitations=[],
    )

    formatted_answer = format_policy_discovery_answer(
        generated_discovery,
        policy_titles={101: "정책 A", 102: "정책 B", 103: "정책 C"},
    )

    assert formatted_answer.startswith("회원님과 관련이 높은 정책 3개를 찾았습니다.")


def test_missing_policy_details_are_displayed_as_confirmation_required() -> None:
    policy = GeneratedPolicyItem(
        policy_id=101,
        summary="기존 summary",
        eligibility_requirements=[],
        exclusion_conditions=[],
        support_details=[],
        application_period=None,
        relevance_reasons=[],
        requirements_to_verify=[],
        cited_source_numbers=[1],
    )
    generated_discovery = GeneratedPolicyDiscovery(
        overview="관련 정책 안내",
        policies=[policy],
        limitations=[],
    )

    formatted_answer = format_policy_discovery_answer(
        generated_discovery,
        policy_titles={101: "테스트 정책"},
    )

    assert formatted_answer.count("- 확인 필요") == 3


def test_support_content_without_money_is_preserved() -> None:
    policy = make_policy(101).model_copy(
        update={"support_details": ["창업 교육과 전문가 멘토링 제공"]}
    )
    generated_discovery = GeneratedPolicyDiscovery(
        overview="관련 정책 안내",
        policies=[policy],
        limitations=[],
    )

    formatted_answer = format_policy_discovery_answer(
        generated_discovery,
        policy_titles={101: "교육 지원정책"},
    )

    assert "[지원 내용]\n- 창업 교육과 전문가 멘토링 제공" in formatted_answer
