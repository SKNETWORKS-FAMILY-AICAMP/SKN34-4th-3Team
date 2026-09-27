from ninja import Router

from api.deps import user_auth
from schemas.bizplan import (
    BizplanCoachRequest,
    BizplanCoachResponse,
    BusinessPlanEvaluateRequest,
    BusinessPlanEvaluateResponse,
    BusinessPlanRefineRequest,
    BusinessPlanRefineResponse,
    BusinessPlanRenderRequest,
    BusinessPlanRenderResponse,
    BusinessPlanRequest,
    BusinessPlanResponse,
    BusinessPlanTemplateRequest,
    BusinessPlanTemplateResponse,
)
from services import bizplan_service

router = Router(tags=["사업계획서"], auth=user_auth)


@router.post("/generate", response=BusinessPlanResponse, summary="사업계획서 초안 생성")
def generate(request, body: BusinessPlanRequest):
    """사업 정보와 선택 공고·양식 또는 사용자가 보완한 항목으로 초안을 만듭니다."""
    return bizplan_service.generate(body.model_dump(), request.auth["id"])


@router.post("/refine", response=BusinessPlanRefineResponse, summary="사업계획서 입력 정리")
def refine(request, body: BusinessPlanRefineRequest):
    """입력된 사실을 추가하거나 삭제하지 않고 읽기 쉬운 문장으로 정리합니다."""
    return bizplan_service.refine(body.model_dump())


@router.post(
    "/template-inspect",
    response=BusinessPlanTemplateResponse,
    summary="사업계획서 양식 검사",
)
def template_inspect(request, body: BusinessPlanTemplateRequest):
    """PDF/HWPX 양식의 입력 위치와 출력 가능 형식을 검사합니다."""
    return bizplan_service.inspect_template(body.model_dump())


@router.post("/evaluate", response=BusinessPlanEvaluateResponse, summary="AI 예비진단(자체 채점)")
def evaluate(request, body: BusinessPlanEvaluateRequest):
    """작성된 초안에 공고·양식 기준을 반영한 점수와 보완점을 제공합니다."""
    return bizplan_service.evaluate(body.model_dump())


@router.post("/render", response=BusinessPlanRenderResponse, summary="사업계획서 파일 출력")
def render(request, body: BusinessPlanRenderRequest):
    """기본 또는 제출 양식으로 HWPX/PDF 파일을 생성합니다."""
    return bizplan_service.render(body.model_dump())


@router.post("/coach", response=BizplanCoachResponse, summary="아이디어 어시스턴트")
def coach(request, body: BizplanCoachRequest):
    """작성 중인 사업계획서 내용을 참고해 아이디어 구체화를 돕습니다. 대화 기록은 저장하지 않습니다."""
    return bizplan_service.coach(body.model_dump())
