from fastapi import APIRouter, Depends, Path

from api.deps import get_current_user
from services import notify_service

router = APIRouter(prefix="/notifications", tags=["알림"])


@router.get("", summary="알림·메일함")
def list_notifications(current: dict = Depends(get_current_user)):
    return {
        "notifications": notify_service.list_notifications(current["id"]),
        "unread": notify_service.unread_count(current["id"]),
    }


@router.post("/{notification_id}/read", summary="알림 읽음")
def read_one(
    notification_id: int = Path(description="알림 ID"),
    current: dict = Depends(get_current_user),
):
    notify_service.mark_read(current["id"], notification_id)
    return {"read": True}


@router.post("/read-all", summary="모든 알림 읽음")
def read_all(current: dict = Depends(get_current_user)):
    notify_service.mark_read(current["id"])
    return {"read": True}


@router.post("/push", summary="지금 브라우저·메일 알림 보내기")
def push_now(body: dict, current: dict = Depends(get_current_user)):
    return notify_service.notify_now(current["id"], int(body["eventId"]))
