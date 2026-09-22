from ninja import Router

from api.deps import user_auth
from schemas.bizplan import BusinessPlanRequest, BusinessPlanResponse
from services import bizplan_service

router = Router(tags=["사업계획서"], auth=user_auth)


@router.post("/generate", response=BusinessPlanResponse, summary="사업계획서 초안 생성")
def generate(request, body: BusinessPlanRequest):
    """입력한 사업 정보만으로 PSST(문제·해결·성장·팀) 구조의 초안을 만듭니다. 법령 근거를 쓰지 않는 일반 생성이라 사실 확인이 필요합니다."""
    return bizplan_service.generate(body.model_dump())
