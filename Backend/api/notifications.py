from ninja import Router, Body, Path

from api.deps import user_auth
from services import notify_service

router = Router(tags=["알림"], auth=user_auth)


@router.get("", summary="알림·메일함")
def list_notifications(request):
    return {
        "notifications": notify_service.list_notifications(request.auth["id"]),
        "unread": notify_service.unread_count(request.auth["id"]),
    }


@router.post("/{notification_id}/read", summary="알림 읽음")
def read_one(
    request,
    notification_id: int = Path(description="알림 ID"),
):
    notify_service.mark_read(request.auth["id"], notification_id)
    return {"read": True}


@router.post("/read-all", summary="모든 알림 읽음")
def read_all(request):
    notify_service.mark_read(request.auth["id"])
    return {"read": True}


@router.post("/push", summary="지금 브라우저·메일 알림 보내기")
def push_now(request, body: dict = Body(...)):
    return notify_service.notify_now(request.auth["id"], int(body["eventId"]))
