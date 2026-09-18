from fastapi import APIRouter, Depends, Query

from api.deps import get_current_user
from schemas.calendar import CalendarCreateRequest, CalendarCreateResponse, CalendarResponse
from services import calendar_service

router = APIRouter(prefix="/calendar", tags=["캘린더"])


@router.get("", response_model=CalendarResponse, summary="홈 화면 통합 캘린더")
def calendar(
    year: int | None = Query(default=None, description="연도"),
    month: int | None = Query(default=None, description="월 (1~12)"),
    type: str | None = Query(default=None, description="일정 종류: tax, policy, user"),
    current: dict = Depends(get_current_user),
):
    """세금·저장/추천 정책 마감일과, 내가 등록한 일정을 조회합니다."""
    return {"events": calendar_service.list_events(year, month, type, current["id"])}


@router.post("", response_model=CalendarCreateResponse, summary="내 일정 등록")
def create_event(body: CalendarCreateRequest, current: dict = Depends(get_current_user)):
    event = calendar_service.create_personal_event(
        current["id"],
        body.title,
        body.dueDate,
        body.description,
        body.remind,
        body.notifyAt,
    )
    return {"event": event}


@router.delete("/{event_id}", summary="내 일정 삭제")
def delete_event(event_id: int, current: dict = Depends(get_current_user)):
    calendar_service.delete_personal_event(current["id"], event_id)
    return {"deleted": True}
