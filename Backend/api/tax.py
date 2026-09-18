from fastapi import APIRouter, Depends, Path, Query

from api.deps import get_current_user
from schemas.calendar import (
    CalendarResponse,
    ReminderCreateRequest,
    ReminderCreateResponse,
    ReminderListResponse,
)
from schemas.tax import (
    DiagnosisRequest,
    DiagnosisResponse,
    TaxInfoResponse,
    TaxInfoUpdate,
    TaxReductionResponse,
)
from services import calendar_service, tax_service

router = APIRouter(prefix="/tax", tags=["세무"])


@router.post(
    "/business-type/diagnosis",
    response_model=DiagnosisResponse,
    summary="사업자 유형 진단",
)
def diagnosis(body: DiagnosisRequest, current: dict = Depends(get_current_user)):
    """예상 매출 등으로 간이/일반과세 안내를 합니다. 법적 확정이 아닙니다."""
    _ = current
    return tax_service.diagnose(body.conditions)


@router.get("/info", response_model=TaxInfoResponse, summary="세금 정보 조회")
def tax_info(current: dict = Depends(get_current_user)):
    """사용자별 세금 메모를 조회합니다."""
    return {"taxInfo": tax_service.get_tax_info(current["id"])}


@router.put("/info", summary="세금 정보 수정")
def update_tax_info(body: TaxInfoUpdate, current: dict = Depends(get_current_user)):
    """사용자별 세금 메모를 저장합니다."""
    tax_service.update_tax_info(current["id"], body.taxInfo)
    return {"updated": True}


@router.get("/calendar", response_model=CalendarResponse, summary="세금 전용 캘린더")
def tax_calendar(
    year: int | None = Query(default=None, description="연도"),
    month: int | None = Query(default=None, description="월 (1~12)"),
    current: dict = Depends(get_current_user),
):
    """세금 신고·납부 일정만 조회합니다. 홈 통합 조회는 GET /calendar 입니다."""
    _ = current
    return {"events": calendar_service.list_events(year, month, "TAX")}


@router.get("/reminders", response_model=ReminderListResponse, summary="리마인더 목록")
def reminders(current: dict = Depends(get_current_user)):
    """등록한 세금/지원금 알림 목록입니다."""
    return {"reminders": calendar_service.list_reminders(current["id"])}


@router.post(
    "/reminders",
    response_model=ReminderCreateResponse,
    summary="리마인더 등록",
)
def create_reminder(body: ReminderCreateRequest, current: dict = Depends(get_current_user)):
    """일정 ID와 알림 시각을 저장합니다. 실제 메일/푸시는 아직 없습니다."""
    reminder_id = calendar_service.create_reminder(current["id"], body.eventId, body.notifyAt)
    return {"reminderId": reminder_id}


@router.delete("/reminders/{reminder_id}", summary="리마인더 삭제")
def delete_reminder(
    reminder_id: int = Path(description="리마인더 ID"),
    current: dict = Depends(get_current_user),
):
    calendar_service.delete_reminder(current["id"], reminder_id)
    return {"deleted": True}


@router.post(
    "/tax-reduction/check",
    response_model=TaxReductionResponse,
    summary="청년창업 세액감면 판정",
)
def tax_reduction_check(current: dict = Depends(get_current_user)):
    """나이·창업일·업종으로 Rule 판정합니다. 온보딩이 있어야 합니다."""
    return tax_service.check_tax_reduction(current["id"])


@router.get(
    "/tax-reduction/result",
    response_model=TaxReductionResponse,
    summary="최근 세액감면 판정 결과",
)
def tax_reduction_result(current: dict = Depends(get_current_user)):
    """마지막으로 실행한 판정 결과를 조회합니다."""
    return tax_service.latest_tax_reduction(current["id"])
