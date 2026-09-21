from ninja import Router, Query

from api.deps import user_auth
from schemas.calendar import CalendarCreateRequest, CalendarCreateResponse, CalendarResponse
from services import calendar_service

router = Router(tags=["캘린더"], auth=user_auth)


@router.get("", response=CalendarResponse, summary="홈 화면 통합 캘린더")
def calendar(
    request,
    year: int | None = Query(default=None, description="연도"),
    month: int | None = Query(default=None, description="월 (1~12)"),
    type: str | None = Query(default=None, description="일정 종류: tax, policy, user"),
):
    """세금·저장/추천 정책 마감일과, 내가 등록한 일정을 조회합니다."""
    return {"events": calendar_service.list_events(year, month, type, request.auth["id"])}


@router.post("", response=CalendarCreateResponse, summary="내 일정 등록")
def create_event(request, body: CalendarCreateRequest):
    event = calendar_service.create_personal_event(
        request.auth["id"],
        body.title,
        body.dueDate,
        body.description,
        body.remind,
        body.notifyAt,
    )
    return {"event": event}


@router.delete("/{event_id}", summary="내 일정 삭제")
def delete_event(request, event_id: int):
    calendar_service.delete_personal_event(request.auth["id"], event_id)
    return {"deleted": True}
