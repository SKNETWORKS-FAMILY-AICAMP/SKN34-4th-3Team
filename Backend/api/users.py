from ninja import Router

from api.deps import user_auth
from schemas.users import (
    BusinessProfileResponse,
    BusinessProfileUpdate,
    UpdatedResponse,
    UserMeResponse,
    UserMeUpdate,
)
from services import user_service

router = Router(tags=["사용자"], auth=user_auth)


@router.get("/me", response=UserMeResponse, summary="내 개인정보 조회")
def me(request):
    """로그인한 사용자의 이름, 나이, 지역을 반환합니다."""
    return user_service.get_me(request.auth["id"])


@router.put("/me", response=UpdatedResponse, summary="내 개인정보 수정")
def update_me(request, body: UserMeUpdate):
    """온보딩에서 나이·지역 등을 저장할 때 사용합니다."""
    user_service.update_me(request.auth["id"], body.model_dump())
    return {"updated": True}


@router.get(
    "/me/business-profile",
    response=BusinessProfileResponse,
    summary="사업자 정보 조회",
)
def business_profile(request):
    """사업자 유형, 업종, 창업일 등을 조회합니다."""
    return user_service.get_business_profile(request.auth["id"])


@router.put(
    "/me/business-profile",
    response=UpdatedResponse,
    summary="사업자 정보 등록/수정",
)
def update_business_profile(
    request,
    body: BusinessProfileUpdate,
):
    """세액감면·정책 추천에 쓰이는 사업자 프로필을 저장합니다."""
    user_service.update_business_profile(request.auth["id"], body.model_dump())
    return {"updated": True}
