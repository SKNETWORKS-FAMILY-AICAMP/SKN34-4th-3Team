"""The reviewed input and selected rubric reach the LLM chains."""

import asyncio
import json

from src.rag.backend_tasks import (
    BUSINESS_PLAN_CONTEXT_MARKER, BUSINESS_PLAN_DEFAULT_FIELDS, BUSINESS_PLAN_EDITS_MARKER,
    BusinessPlanFieldAnalysis, analyze_business_plan_fields,
    BusinessPlanEvaluation, BusinessPlanGeneration, BusinessPlanRefinement,
    _clear_unprovided_table_cells, _normalize_plan_table,
    evaluate_business_plan, generate_business_plan, refine_business_plan_input,
)
from tests.fakes import FakeStructuredChatModel
from src.serving.rag_routes import RagRuntime, adapter_business_plan
from src.serving.schemas import BusinessPlanRequest


def test_reviewed_refinement_feeds_template_draft_without_inventing_empty_field() -> None:
    model = FakeStructuredChatModel({
        BusinessPlanRefinement: {
            "businessName": "정리된 사업명", "tagline": "", "startupStatus": "예비창업자",
            "industry": "정보통신업", "businessRegion": "서울", "businessType": "1인 창업",
            "targetCustomer": "고객", "problem": "문제",
            "solution": "정리된 해결책", "coreFeatures": "발주 추천",
            "differentiator": "지어낸 차별점", "revenueModel": "월 구독",
            "team": "개발자 1명", "extraNotes": "",
        },
        BusinessPlanGeneration: {
            "sections": [{"key": "section_1", "label": "문제인식", "content": "고객의 문제"}],
            "summary": "검토된 정보의 요약",
        },
    })
    source = {
        "businessName": "사업명", "tagline": "", "startupStatus": "예비창업자",
        "industry": "정보통신업", "businessRegion": "서울", "businessType": "1인 창업",
        "targetCustomer": "고객", "problem": "문제",
        "solution": "해결책", "coreFeatures": "발주 추천", "differentiator": "",
        "revenueModel": "월 구독", "team": "개발자 1명", "extraNotes": "",
    }
    refined = asyncio.run(refine_business_plan_input(model, source))
    assert refined.differentiator == ""
    reviewed = refined.model_copy(update={"solution": "사용자가 수정한 해결책"})

    draft = asyncio.run(generate_business_plan(
        model,
        business_name=reviewed.businessName, tagline=reviewed.tagline,
        startup_status=reviewed.startupStatus, industry=reviewed.industry,
        business_region=reviewed.businessRegion, business_type=reviewed.businessType,
        target_customer=reviewed.targetCustomer, problem_input=reviewed.problem,
        solution_input=reviewed.solution, core_features=reviewed.coreFeatures,
        differentiator=reviewed.differentiator, revenue_model=reviewed.revenueModel,
        team_input=reviewed.team, target_program="선택 공고", extra_notes=reviewed.extraNotes,
        template_fields=["문제인식", "성장계획"], announcement_criteria="사업성 40점",
    ))
    assert "사용자가 수정한 해결책" in model.last_prompt_text
    assert "예비창업자" in model.last_prompt_text
    assert "발주 추천" in model.last_prompt_text
    assert "월 구독" in model.last_prompt_text
    assert "사업성 40점" in model.last_prompt_text
    assert [section.label for section in draft.sections] == ["문제인식", "성장계획"]
    assert draft.sections[1].content == ""
    assert "기본 사업계획서의 13개 항목이나 PSST 구성을 적용하거나" in model.last_prompt_text
    assert "content를 빈 문자열로 두세요" in model.last_prompt_text


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


def test_default_draft_returns_every_default_form_field() -> None:
    first_key, first_label, _ = BUSINESS_PLAN_DEFAULT_FIELDS[0]
    model = FakeStructuredChatModel({BusinessPlanGeneration: {
        "sections": [{"key": first_key, "label": first_label, "content": "예비창업자 신청"}],
        "summary": "기본 양식 초안",
    }})
    draft = asyncio.run(generate_business_plan(
        model,
        business_name="사업명", tagline="", startup_status="예비창업자",
        industry="정보통신업", business_region="서울", business_type="1인 창업",
        target_customer="소상공인", problem_input="재고 오차", solution_input="자동 발주",
        core_features="발주 추천", differentiator="실시간 분석", revenue_model="월 구독",
        team_input="개발자 1명", target_program="예비창업패키지", extra_notes="",
    ))
    assert [(section.key, section.label) for section in draft.sections] == [
        (key, label) for key, label, _ in BUSINESS_PLAN_DEFAULT_FIELDS
    ]
    assert draft.sections[0].content == "예비창업자 신청"
    assert draft.sections[-1].content == "정보 부족"


def test_text_template_keeps_its_own_sections_instead_of_default_fields() -> None:
    model = FakeStructuredChatModel({BusinessPlanGeneration: {
        "sections": [{"key": "section_1", "label": "고객 요구", "content": ""}],
        "summary": "사용자가 제공한 내용의 요약",
    }})
    draft = asyncio.run(generate_business_plan(
        model,
        business_name="사업명", tagline="", startup_status="예비창업자",
        industry="정보통신업", business_region="서울", business_type="1인 창업",
        target_customer="고객", problem_input="", solution_input="",
        core_features="", differentiator="", revenue_model="", team_input="",
        target_program="", extra_notes="", template_text="고객 요구",
    ))
    assert [(section.label, section.content) for section in draft.sections] == [("고객 요구", "")]
    assert "기본 사업계획서의 13개 항목이나 PSST 구성을 적용하거나" in model.last_prompt_text


def test_regenerated_draft_uses_reviewed_sections_as_source() -> None:
    model = FakeStructuredChatModel({BusinessPlanGeneration: {
        "sections": [{"key": "section_1", "label": "시장 분석", "content": "보완한 시장 분석"}],
        "summary": "보완한 초안 요약",
    }})
    draft = asyncio.run(generate_business_plan(
        model,
        business_name="사업명", tagline="", startup_status="예비창업자",
        industry="정보통신업", business_region="서울", business_type="1인 창업",
        target_customer="소상공인", problem_input="재고 오차", solution_input="자동 발주",
        core_features="발주 추천", differentiator="실시간 분석", revenue_model="월 구독",
        team_input="개발자 1명", target_program="", extra_notes="",
        reviewed_sections=[{"key": "section_1", "label": "시장 분석", "content": "실제 고객 조사 20건을 추가했습니다."}],
    ))
    assert "실제 고객 조사 20건을 추가했습니다." in model.last_prompt_text
    assert [(section.key, section.label) for section in draft.sections] == [("section_1", "시장 분석")]


def test_field_analysis_maps_user_facts_and_marks_missing_schedule() -> None:
    model = FakeStructuredChatModel({BusinessPlanFieldAnalysis: {"fields": [
        {"field_id": "section_1", "type": "text", "instruction": "시장 진입 방법",
         "required_information": ["초기 고객 확보 방법"], "status": "ready",
         "missing_fields": [], "missing_reason": "", "mapped_information": ["저렴한 구독료"]},
        {"field_id": "section_2", "type": "table", "instruction": "사업 추진일정",
         "required_information": ["추진내용", "추진기간", "세부내용"], "status": "missing",
         "missing_fields": ["추진기간"], "missing_reason": "기간 정보가 없음",
         "mapped_information": []},
    ]}})
    analysis = asyncio.run(analyze_business_plan_fields(
        model, template_fields=["시장진입 전략", "사업 추진일정 [표: 추진내용 | 추진기간 | 세부내용]"],
        user_information={"수익 방식": "저렴한 구독료와 주문 수수료"},
    ))
    assert [field.status for field in analysis.fields] == ["ready", "missing"]
    assert analysis.fields[1].missing_fields == ["추진기간"]
    assert "저렴한 구독료와 주문 수수료" in model.last_prompt_text


def test_field_analysis_batches_large_templates_with_original_field_ids() -> None:
    from langchain_core.runnables import RunnableLambda

    class BatchModel:
        def __init__(self) -> None:
            self.prompts = []

        def with_structured_output(self, schema):
            async def respond(prompt):
                text = prompt.to_string()
                self.prompts.append(text)
                fields = []
                for index in range(1, 18):
                    if f"section_{index}: 항목 {index}" in text:
                        fields.append({
                            "field_id": f"section_{index}", "type": "text",
                            "instruction": f"항목 {index}", "required_information": [],
                            "status": "ready", "missing_fields": [],
                            "missing_reason": "", "mapped_information": ["입력값"],
                        })
                return schema.model_validate({"fields": fields})

            return RunnableLambda(respond)

    model = BatchModel()
    result = asyncio.run(analyze_business_plan_fields(
        model, template_fields=[f"항목 {index}" for index in range(1, 18)],
        user_information={"사업명": "입력값"},
    ))
    assert len(model.prompts) == 3
    assert [field.field_id for field in result.fields] == [
        f"section_{index}" for index in range(1, 18)
    ]
    assert all(field.status == "ready" for field in result.fields)
    assert any("section_17: 항목 17" in prompt for prompt in model.prompts)


def test_draft_batches_large_templates_without_repeating_other_fields() -> None:
    from langchain_core.runnables import RunnableLambda

    class BatchModel:
        def __init__(self) -> None:
            self.prompts = []

        def with_structured_output(self, schema):
            async def respond(prompt):
                text = prompt.to_string()
                self.prompts.append(text)
                lines = set(text.splitlines())
                return schema.model_validate({
                    "sections": [
                        {"key": f"section_{index}", "label": f"항목 {index}",
                         "content": f"내용 {index}"}
                        for index in range(1, 18)
                        if f"{index}. 항목 {index}" in lines
                    ],
                    "summary": "요약",
                })

            return RunnableLambda(respond)

    model = BatchModel()
    result = asyncio.run(generate_business_plan(
        model, business_name="사업", tagline="", startup_status="예비창업자",
        industry="", business_region="", business_type="",
        target_customer="", problem_input="", solution_input="",
        core_features="", differentiator="", revenue_model="",
        team_input="", target_program="", extra_notes="",
        template_fields=[f"항목 {index}" for index in range(1, 18)],
    ))
    assert len(model.prompts) == 3
    assert [section.content for section in result.sections] == [
        f"내용 {index}" for index in range(1, 18)
    ]
    assert all(sum(f"{index}. 항목 {index}" in prompt.splitlines()
                   for index in range(1, 18)) <= 8
               for prompt in model.prompts)


def test_profile_name_is_ready_and_missing_personal_details_require_supplement() -> None:
    fields = ["창업아이템명 [유형: metadata]", "신청자 성명 [유형: metadata]",
              "생년월일 [유형: metadata]", "기업명 [유형: metadata]",
              "정부지원금 [유형: metadata]"]
    model = FakeStructuredChatModel({BusinessPlanFieldAnalysis: {"fields": [
        {"field_id": f"section_{index}", "type": "metadata", "instruction": label,
         "required_information": [], "status": "ready", "missing_fields": [],
         "missing_reason": "", "mapped_information": ["추정값"]}
        for index, label in enumerate(fields[:4], 1)
    ]}})
    analysis = asyncio.run(analyze_business_plan_fields(
        model, template_fields=fields,
        user_information={"사업명": "재고관리 서비스", "신청자 성명": "신대호"},
    ))
    assert [field.status for field in analysis.fields] == [
        "ready", "ready", "missing", "missing", "missing",
    ]
    assert analysis.fields[1].mapped_information == ["신대호"]
    assert analysis.fields[2].missing_fields == ["생년월일"]
    assert analysis.fields[3].missing_fields == ["기업명"]
    assert analysis.fields[4].missing_fields == ["정부지원금"]


def test_personal_metadata_uses_profile_or_explicit_supplement_value() -> None:
    fields = ["창업아이템명 [유형: metadata]", "신청자 성명 [유형: metadata]",
              "생년월일 [유형: metadata]", "기업명 [유형: metadata]"]
    model = FakeStructuredChatModel({BusinessPlanGeneration: {
        "sections": [{"key": f"section_{index}", "label": label, "content": "추정값"}
                     for index, label in enumerate(fields, 1)],
        "summary": "사업계획서 요약",
    }})
    context = BUSINESS_PLAN_CONTEXT_MARKER + json.dumps({"fields": [
        {"id": "section_3", "status": "ready", "answers": {"생년월일": "1990.01.02"}},
        {"id": "section_4", "status": "missing", "answers": {}},
    ]}, ensure_ascii=False)
    draft = asyncio.run(generate_business_plan(
        model, business_name="재고관리 서비스", applicant_name="신대호", tagline="",
        startup_status="예비창업자", industry="정보통신업", business_region="서울",
        business_type="1인 창업", target_customer="", problem_input="", solution_input="",
        core_features="", differentiator="", revenue_model="", team_input="",
        target_program="", extra_notes="", template_fields=fields, template_text=context,
    ))
    assert [section.content for section in draft.sections] == [
        "재고관리 서비스", "신대호", "1990.01.02", "",
    ]


def test_template_context_keeps_unsupported_and_unanswered_fields_blank() -> None:
    model = FakeStructuredChatModel({BusinessPlanGeneration: {
        "sections": [
            {"key": "section_1", "label": "사업 추진일정", "content": "임의의 2027년 일정"},
            {"key": "section_2", "label": "제품 사진", "content": "가상 사진"},
        ], "summary": "사업계획서 요약",
    }})
    context = BUSINESS_PLAN_CONTEXT_MARKER + (
        '[{"id":"section_1","status":"missing","answers":{},"mapped":[]},'
        '{"id":"section_2","status":"unsupported","answers":{},"mapped":[]}]'
    )
    draft = asyncio.run(generate_business_plan(
        model, business_name="사업", tagline="", startup_status="예비창업자",
        industry="정보통신업", business_region="서울", business_type="1인 창업",
        target_customer="고객", problem_input="문제", solution_input="해결",
        core_features="기능", differentiator="차별점", revenue_model="수수료",
        team_input="1명", target_program="", extra_notes="",
        template_fields=["사업 추진일정", "제품 사진"], template_text=context,
    ))
    assert [section.content for section in draft.sections] == ["", ""]


def test_analysis_uses_existing_generate_response_contract() -> None:
    model = FakeStructuredChatModel({BusinessPlanFieldAnalysis: {"fields": [{
        "field_id": "section_1", "type": "table", "instruction": "추진기간을 작성",
        "required_information": ["추진내용", "추진기간", "세부내용"],
        "status": "partial", "missing_fields": ["추진기간"],
        "missing_reason": "일정 정보가 없습니다.", "mapped_information": ["MVP 개발"],
    }]}})
    response = asyncio.run(adapter_business_plan(
        BusinessPlanRequest(
            templateText="__FIELD_ANALYSIS_V1__",
            templateFields=["2-1. 사업 추진일정 [표: 추진내용 | 추진기간 | 세부내용]"],
            coreFeatures="MVP 개발",
        ), RagRuntime(llm_factory=lambda: model), None,
    ))
    assert response.sections[0].key == "section_1"
    assert json.loads(response.sections[0].content)["missing_fields"] == ["추진기간"]
    assert model.call_count == 1


def test_analysis_accepts_explicit_not_applicable_status() -> None:
    model = FakeStructuredChatModel({BusinessPlanFieldAnalysis: {"fields": [{
        "field_id": "section_1", "type": "multiline_text", "instruction": "해외 진출 계획",
        "required_information": ["진출 국가"], "status": "not_applicable",
        "missing_fields": [], "missing_reason": "", "mapped_information": ["해외 진출 계획 없음"],
    }]}})
    result = asyncio.run(analyze_business_plan_fields(
        model, template_fields=["해외시장 진출 계획"],
        user_information={"추가 설명": "현재 해외 진출 계획 없음"},
    ))
    assert result.fields[0].status == "not_applicable"


def test_image_field_requests_an_uploaded_file_instead_of_unsupported_status() -> None:
    model = FakeStructuredChatModel({BusinessPlanFieldAnalysis: {"fields": [{
        "field_id": "section_1", "type": "image", "instruction": "제품 사진",
        "required_information": [], "status": "unsupported", "missing_fields": [],
        "missing_reason": "", "mapped_information": [],
    }]}})
    for label in ("제품 사진 [유형: image]", "제품 사진"):
        result = asyncio.run(analyze_business_plan_fields(
            model, template_fields=[label], user_information={},
        ))
        assert result.fields[0].status == "missing"
        assert result.fields[0].type == "image"
        assert result.fields[0].missing_fields == ["이미지 파일"]


def test_not_applicable_and_table_rows_use_structured_content() -> None:
    model = FakeStructuredChatModel({BusinessPlanGeneration: {
        "sections": [
            {"key": "section_1", "label": "해외시장 진출", "content": "임의의 해외 진출 계획"},
            {"key": "section_2", "label": "추진일정 [표: 추진내용 | 추진기간 | 세부내용]",
             "content": "MVP 개발 | 2026년 10월 | 핵심 기능 구현"},
        ], "summary": "사업계획서 요약",
    }})
    context = BUSINESS_PLAN_CONTEXT_MARKER + json.dumps({"fields": [
        {"id": "section_1", "type": "multiline_text", "status": "not_applicable", "answers": {}},
        {"id": "section_2", "type": "table", "status": "ready", "answers": {"추진기간": "2026년 10월"}},
    ]}, ensure_ascii=False)
    draft = asyncio.run(generate_business_plan(
        model, business_name="사업", tagline="", startup_status="예비창업자",
        industry="정보통신업", business_region="서울", business_type="1인 창업",
        target_customer="고객", problem_input="문제", solution_input="해결",
        core_features="MVP 개발", differentiator="", revenue_model="", team_input="",
        target_program="", extra_notes="",
        template_fields=["해외시장 진출", "추진일정 [표: 추진내용 | 추진기간 | 세부내용]"],
        template_text=context,
    ))
    assert draft.sections[0].content == "해당 사항 없음"
    assert json.loads(draft.sections[1].content) == {"rows": [{
        "추진내용": "MVP 개발", "추진기간": "2026년 10월", "세부내용": "핵심 기능 구현",
    }]}


def test_ai_polish_preserves_user_edited_section_exactly() -> None:
    model = FakeStructuredChatModel({BusinessPlanGeneration: {
        "sections": [{"key": "motivation", "label": "개발 동기", "content": "AI가 바꾼 내용"}],
        "summary": "수정 내용을 반영한 요약",
    }})
    draft = asyncio.run(generate_business_plan(
        model, business_name="사업", tagline="", startup_status="예비창업자",
        industry="정보통신업", business_region="서울", business_type="1인 창업",
        target_customer="고객", problem_input="문제", solution_input="해결",
        core_features="기능", differentiator="", revenue_model="", team_input="",
        target_program="", extra_notes="",
        reviewed_sections=[{"key": "motivation", "label": "개발 동기", "content": "사용자가 직접 쓴 동기"}],
        template_text=BUSINESS_PLAN_EDITS_MARKER + '["motivation"]',
    ))
    assert draft.sections[0].content == "사용자가 직접 쓴 동기"
    assert "사용자 직접 수정 항목 key: motivation" in model.last_prompt_text


def test_partial_schedule_drops_unprovided_period_from_generated_table() -> None:
    label = "사업 추진일정 [표: 추진내용 | 추진기간 | 세부내용]"
    model = FakeStructuredChatModel({BusinessPlanGeneration: {
        "sections": [{"key": "section_1", "label": label,
                      "content": '{"rows":[{"추진내용":"MVP 개발","추진기간":"2027년 3월",'
                                 '"세부내용":"핵심 기능 구현"}]}'}],
        "summary": "사업 추진계획 요약",
    }})
    context = BUSINESS_PLAN_CONTEXT_MARKER + json.dumps({"fields": [{
        "id": "section_1", "type": "table", "status": "partial",
        "missing": ["추진기간"], "answers": {"추진기간": ""}, "mapped": ["MVP 개발"],
    }]}, ensure_ascii=False)
    draft = asyncio.run(generate_business_plan(
        model, business_name="사업", tagline="", startup_status="예비창업자",
        industry="정보통신업", business_region="서울", business_type="1인 창업",
        target_customer="고객", problem_input="문제", solution_input="해결",
        core_features="MVP 개발", differentiator="", revenue_model="", team_input="",
        target_program="", extra_notes="", template_fields=[label], template_text=context,
    ))
    row = json.loads(draft.sections[0].content)["rows"][0]
    assert row["추진내용"] == "MVP 개발"
    assert row["추진기간"] is None


def test_table_rejects_unprovided_amounts_even_outside_explicit_missing_columns() -> None:
    content = json.dumps({"rows": [{"비목": "외주용역비", "사업비": "100만원"}]}, ensure_ascii=False)
    result = _clear_unprovided_table_cells(content, {"mapped": ["외주용역비"], "answers": {}})
    assert json.loads(result)["rows"] == [{"비목": "외주용역비", "사업비": None}]


def test_table_treats_information_shortage_as_an_empty_field() -> None:
    assert _normalize_plan_table("정보 부족", "사업비 [표: 비목 | 사업비]") == ""
