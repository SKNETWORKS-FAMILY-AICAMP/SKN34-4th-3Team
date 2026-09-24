from ninja import File, Router
from ninja.files import UploadedFile

from api.deps import user_auth
from schemas.bizplan import (
    BizplanCoachRequest,
    BizplanCoachResponse,
    BusinessPlanEvaluateRequest,
    BusinessPlanEvaluateResponse,
    BusinessPlanRequest,
    BusinessPlanResponse,
    BusinessPlanTemplateFileResponse,
)
from services import bizplan_service

router = Router(tags=["사업계획서"], auth=user_auth)


@router.post("/generate", response=BusinessPlanResponse, summary="사업계획서 초안 생성")
def generate(request, body: BusinessPlanRequest):
    """입력한 사업 정보로 초안을 만듭니다. templateText(지원사업 공고 양식)를 주면 그 항목 구성을 따르고, 비워두면 PSST(문제·해결·성장·팀) 4항목으로 만듭니다. 법령 근거를 쓰지 않는 일반 생성이라 사실 확인이 필요합니다."""
    return bizplan_service.generate(body.model_dump())


@router.post("/evaluate", response=BusinessPlanEvaluateResponse, summary="AI 예비진단(자체 채점)")
def evaluate(request, body: BusinessPlanEvaluateRequest):
    """작성된 PSST 초안에 항목별 점수·강점·보완점을 매깁니다. 실제 심사 결과가 아닌 참고용입니다."""
    return bizplan_service.evaluate(body.model_dump())


@router.post("/coach", response=BizplanCoachResponse, summary="아이디어 어시스턴트")
def coach(request, body: BizplanCoachRequest):
    """작성 중인 사업계획서 내용을 참고해 아이디어 구체화를 돕습니다. 대화 기록은 저장하지 않습니다."""
    return bizplan_service.coach(body.model_dump())


@router.post("/template-file", response=BusinessPlanTemplateFileResponse, summary="공고 양식 파일에서 텍스트 추출")
def template_file(request, file: UploadedFile = File(..., description="지원사업 공고 첨부 사업계획서 양식(PDF)")):
    """올린 PDF에서 텍스트만 뽑아 돌려줍니다. 이 텍스트를 그대로 /generate의 templateText로 보내면 됩니다."""
    return bizplan_service.extract_template_file(
        file.name or "template.pdf",
        file.read(),
        file.content_type or "application/pdf",
    )
