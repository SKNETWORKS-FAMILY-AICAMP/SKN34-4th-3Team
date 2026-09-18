from datetime import datetime
from email.message import EmailMessage
import smtplib

from core import repo
from core.config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER


def list_notifications(user_id: int) -> list[dict]:
    dispatch_due_reminders()
    rows = repo.list_notifications(user_id)
    return [_to_item(item) for item in rows]


def unread_count(user_id: int) -> int:
    return repo.unread_count(user_id)


def mark_read(user_id: int, notification_id: int | None = None) -> None:
    repo.mark_notifications_read(user_id, notification_id)


def dispatch_due_reminders() -> int:
    created = 0
    now = datetime.now()
    for reminder in repo.due_reminders():
        notify_at = reminder.get("notify_at")
        if isinstance(notify_at, str):
            notify_at = datetime.fromisoformat(notify_at)
        if not notify_at or notify_at > now:
            continue
        event = repo.get_event(reminder["event_id"])
        if not event:
            continue
        user = repo.get_user(reminder["user_id"]) or {}
        title = f"일정 알림: {event['title']}"
        body = f"{event['title']} 마감은 {event['due_date']}입니다. 앱에서 일정을 확인하세요."
        phone = (user.get("phone") or "").strip()
        _create_notification(reminder["user_id"], "reminder", title, body, "in_app")
        _create_notification(reminder["user_id"], "push", title, body, "push")
        email_status = _send_email(user.get("email") or "", title, body)
        _create_notification(reminder["user_id"], "email", title, body, "email", email_status)
        sms_status = _queue_sms(phone, f"{title} {body}")
        _create_notification(
            reminder["user_id"],
            "sms",
            title,
            f"{phone or '번호 없음'} · {body}" if phone else "휴대폰 번호가 없어 문자는 보내지 않았습니다.",
            "sms",
            sms_status,
        )
        repo.mark_reminder_dispatched(reminder["id"])
        created += 1
    return created


def notify_now(user_id: int, event_id: int) -> dict:
    event = repo.get_event(event_id)
    if not event:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
    title = f"일정 알림: {event['title']}"
    body = f"{event['title']} 마감은 {event['due_date']}입니다."
    user = repo.get_user(user_id) or {}
    in_app = _create_notification(user_id, "push", title, body, "push")
    email_status = _send_email(user.get("email") or "", title, body)
    _create_notification(user_id, "email", title, body, "email", email_status)
    return {"notificationId": in_app, "emailStatus": email_status}


def _create_notification(
    user_id: int,
    kind: str,
    title: str,
    body: str,
    channel: str,
    status: str = "delivered",
) -> int:
    return repo.insert_notification(user_id, kind, title, body, channel, status)


def _send_email(to_email: str, subject: str, body: str) -> str:
    if not to_email:
        return "skipped"
    if not SMTP_HOST:
        return "queued-local"
    try:
        message = EmailMessage()
        message["From"] = SMTP_FROM
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=8) as smtp:
            smtp.starttls()
            if SMTP_USER:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(message)
        return "sent"
    except Exception:
        return "failed"


def _queue_sms(phone: str, text: str) -> str:
    if not phone:
        return "skipped"
    return "queued-local"


def _to_item(item: dict) -> dict:
    return {
        "id": item["id"],
        "kind": item["kind"],
        "title": item["title"],
        "body": item["body"],
        "channel": item["channel"],
        "status": item["status"],
        "read": bool(item.get("read")),
        "createdAt": item["created_at"],
    }
