"""The reviewed input and selected rubric reach the LLM chains."""

import asyncio

from src.rag.backend_tasks import (
    BusinessPlanEvaluation, BusinessPlanGeneration, BusinessPlanRefinement,
    evaluate_business_plan, generate_business_plan, refine_business_plan_input,
)
from tests.fakes import FakeStructuredChatModel


def test_reviewed_refinement_feeds_template_draft_without_inventing_empty_field() -> None:
    model = FakeStructuredChatModel({
        BusinessPlanRefinement: {
            "businessName": "정리된 사업명", "tagline": "소개", "targetCustomer": "고객",
            "problem": "문제", "solution": "정리된 해결책", "differentiator": "지어낸 차별점",
            "team": "", "extraNotes": "",
        },
        BusinessPlanGeneration: {
            "sections": [{"key": "section_1", "label": "문제인식", "content": "고객의 문제"}],
            "summary": "검토된 정보의 요약",
        },
    })
    source = {
        "businessName": "사업명", "tagline": "소개", "targetCustomer": "고객", "problem": "문제",
        "solution": "해결책", "differentiator": "", "team": "", "extraNotes": "",
    }
    refined = asyncio.run(refine_business_plan_input(model, source))
    assert refined.differentiator == ""
    reviewed = refined.model_copy(update={"solution": "사용자가 수정한 해결책"})

    draft = asyncio.run(generate_business_plan(
        model,
        business_name=reviewed.businessName, tagline=reviewed.tagline,
        target_customer=reviewed.targetCustomer, problem_input=reviewed.problem,
        solution_input=reviewed.solution, differentiator=reviewed.differentiator,
        team_input=reviewed.team, target_program="선택 공고", extra_notes=reviewed.extraNotes,
        template_fields=["문제인식", "성장계획"], announcement_criteria="사업성 40점",
    ))
    assert "사용자가 수정한 해결책" in model.last_prompt_text
    assert "사업성 40점" in model.last_prompt_text
    assert [section.label for section in draft.sections] == ["문제인식", "성장계획"]
    assert draft.sections[1].content == "정보 부족"


def test_evaluation_uses_selected_announcement_criteria() -> None:
    model = FakeStructuredChatModel({BusinessPlanEvaluation: {
        "overall_score": 55, "overall_comment": "시장 규모 근거가 부족합니다.",
        "sections": [{"key": "problem", "label": "문제인식", "score": 55,
                      "strengths": "문제를 설명했습니다.",
                      "improvements": "시장 규모의 출처가 필요합니다."}],
    }})
    result = asyncio.run(evaluate_business_plan(
        model, sections=[{"key": "problem", "label": "문제인식", "content": "고객 문제"}],
        announcement_criteria="시장성 50점", template_criteria="근거 자료 명시",
    ))
    assert result.overall_score == 55
    assert result.sections[0].improvements
    assert "시장성 50점" in model.last_prompt_text
    assert "근거 자료 명시" in model.last_prompt_text
