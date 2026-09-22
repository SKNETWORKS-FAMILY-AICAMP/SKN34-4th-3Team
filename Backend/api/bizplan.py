from fastapi import APIRouter, Depends

from api.deps import get_current_user
from schemas.bizplan import BusinessPlanRequest, BusinessPlanResponse
from services import bizplan_service

router = APIRouter(prefix="/bizplan", tags=["사업계획서"])


@router.post("/generate", response_model=BusinessPlanResponse, summary="사업계획서 초안 생성")
def generate(body: BusinessPlanRequest, current: dict = Depends(get_current_user)):
    """입력한 사업 정보만으로 PSST(문제·해결·성장·팀) 구조의 초안을 만듭니다. 법령 근거를 쓰지 않는 일반 생성이라 사실 확인이 필요합니다."""
    _ = current
    return bizplan_service.generate(body.model_dump())
