from ninja import Router

from core import repo
from core.config import MAX_REDUCTION_RATE
from schemas.stats import StatsResponse

router = Router(tags=["상태"])


@router.get("/stats", response=StatsResponse, summary="서비스 지표")
def stats(request):
    """홈 화면 상단에 표시할 수집 현황입니다. 로그인 없이 조회할 수 있습니다."""
    return {
        "openAnnouncements": repo.count_open_announcements(),
        "policies": repo.count("policies"),
        "taxDocuments": repo.count("tax_documents"),
        "maxReductionRate": MAX_REDUCTION_RATE,
    }
