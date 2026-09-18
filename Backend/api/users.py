from fastapi import APIRouter, Depends

from api.deps import get_current_user
from schemas.users import (
    BusinessProfileResponse,
    BusinessProfileUpdate,
    UpdatedResponse,
    UserMeResponse,
    UserMeUpdate,
)
from services import user_service

router = APIRouter(prefix="/users", tags=["사용자"])


@router.get("/me", response_model=UserMeResponse, summary="내 개인정보 조회")
def me(current: dict = Depends(get_current_user)):
    """로그인한 사용자의 이름, 나이, 지역을 반환합니다."""
    return user_service.get_me(current["id"])


@router.put("/me", response_model=UpdatedResponse, summary="내 개인정보 수정")
def update_me(body: UserMeUpdate, current: dict = Depends(get_current_user)):
    """온보딩에서 나이·지역 등을 저장할 때 사용합니다."""
    user_service.update_me(current["id"], body.model_dump())
    return {"updated": True}


@router.get(
    "/me/business-profile",
    response_model=BusinessProfileResponse,
    summary="사업자 정보 조회",
)
def business_profile(current: dict = Depends(get_current_user)):
    """사업자 유형, 업종, 창업일 등을 조회합니다."""
    return user_service.get_business_profile(current["id"])


@router.put(
    "/me/business-profile",
    response_model=UpdatedResponse,
    summary="사업자 정보 등록/수정",
)
def update_business_profile(
    body: BusinessProfileUpdate, current: dict = Depends(get_current_user)
):
    """세액감면·정책 추천에 쓰이는 사업자 프로필을 저장합니다."""
    user_service.update_business_profile(current["id"], body.model_dump())
    return {"updated": True}
