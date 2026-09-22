from ninja import Router, Path, Query

from api.deps import user_auth
from schemas.policies import (
    AnnouncementListResponse,
    AnnouncementSummaryRequest,
    AnnouncementSummaryResponse,
    EligibilityResponse,
    PolicyDetailResponse,
    PolicyListResponse,
    SavedResponse,
)
from services import policy_service

router = Router(tags=["지원정책"], auth=user_auth)


@router.get(
    "/announcements",
    response=AnnouncementListResponse,
    auth=None,
    summary="모집 중 공고 목록",
)
def announcements(
    request,
    limit: int = Query(default=20, ge=1, le=100, description="가져올 공고 수"),
):
    """마감이 지나지 않은 공고를 마감 임박순으로 반환합니다.

    공고는 공개 정보이므로 로그인 없이 조회할 수 있습니다.
    """
    return {"announcements": policy_service.list_open_announcements(limit)}


@router.get("/policies", response=PolicyListResponse, summary="지원정책 검색")
def search(
    request,
    keyword: str | None = Query(default=None, description="검색 키워드"),
    region: str | None = Query(default=None, description="지역 (예: 서울)"),
    industry: str | None = Query(default=None, description="업종"),
    page: int = Query(default=1, ge=1, description="페이지 번호"),
    size: int = Query(default=20, ge=1, le=100, description="페이지당 건수"),
):
    """키워드·지역·업종으로 정책을 검색합니다. 자격 충족·점수 순으로 정렬됩니다."""
    return {
        "policies": policy_service.search(
            keyword, region, industry, request.auth["id"], offset=(page - 1) * size, limit=size
        )
    }


@router.get(
    "/policies/recommendations",
    response=PolicyListResponse,
    summary="맞춤 정책 추천",
)
def recommendations(
    request,
    limit: int = Query(default=20, ge=1, le=50, description="추천 건수"),
):
    """온보딩 프로필과 정책 요건을 비교해 상위 건을 추천합니다."""
    return {"policies": policy_service.recommendations(request.auth["id"], limit=limit)}


@router.get("/policies/saved", response=PolicyListResponse, summary="관심 정책 목록")
def saved(request):
    """저장한 관심 정책 목록입니다."""
    return {"policies": policy_service.saved_list(request.auth["id"])}


@router.get("/policies/{policy_id}", response=PolicyDetailResponse, summary="정책 상세")
def detail(
    request,
    policy_id: int = Path(description="정책 ID"),
):
    """신청기간·신청방법을 포함한 정책 상세입니다."""
    return policy_service.detail(policy_id)


@router.get(
    "/policies/{policy_id}/eligibility",
    response=EligibilityResponse,
    summary="지원 자격 확인",
)
def eligibility(
    request,
    policy_id: int = Path(description="정책 ID"),
):
    """내 프로필과 정책 요건을 비교합니다."""
    return policy_service.eligibility(policy_id, request.auth["id"])


@router.post(
    "/policies/{policy_id}/save",
    response=SavedResponse,
    summary="관심 정책 저장",
)
def save(
    request,
    policy_id: int = Path(description="정책 ID"),
):
    policy_service.save_policy(request.auth["id"], policy_id)
    return {"saved": True}


@router.delete(
    "/policies/{policy_id}/save",
    response=SavedResponse,
    summary="관심 정책 저장 해제",
)
def unsave(
    request,
    policy_id: int = Path(description="정책 ID"),
):
    policy_service.unsave_policy(request.auth["id"], policy_id)
    return {"saved": False}


@router.get(
    "/announcements/{announcement_id}/summary",
    response=AnnouncementSummaryResponse,
    summary="공고문 요약 조회",
)
def summary(
    request,
    announcement_id: int = Path(description="공고 ID"),
):
    """저장된 요약이 있으면 쓰고, LLM 서비스가 있으면 다시 요약합니다."""
    return policy_service.announcement_summary(announcement_id)


@router.post(
    "/announcements/summary",
    response=AnnouncementSummaryResponse,
    summary="붙여넣은 공고문 요약",
)
def summarize_pasted(
    request,
    body: AnnouncementSummaryRequest,
):
    """저장되지 않은 공고문 원문을 LLM 서비스로 구조화합니다.

    DB에 없는 임의 텍스트를 다루므로 요약을 캐시하지 않습니다.
    """
    return policy_service.summarize_text(body.rawContent, body.source)
