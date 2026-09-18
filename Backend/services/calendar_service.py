from datetime import date, datetime

from fastapi import HTTPException

from core import repo


def _to_item(event: dict, user_id: int | None = None) -> dict:
    return {
        "id": event["id"],
        "eventType": event["event_type"],
        "title": event["title"],
        "dueDate": event["due_date"],
        "description": event["description"] or "",
        "policyId": event.get("policy_id"),
        "mine": event["event_type"] == "USER" and event.get("user_id") == user_id,
    }


def list_events(
    year: int | None,
    month: int | None,
    event_type: str | None = None,
    user_id: int | None = None,
) -> list[dict]:
    rows = repo.list_events()
    if event_type:
        rows = [e for e in rows if (e["event_type"] or "").lower() == event_type.lower()]
    if user_id is not None:
        # POLICY 일정은 내가 저장한 정책이거나 아직 마감 전인 것만 보여준다.
        # 예전에는 추천 목록으로 걸렀는데, 추천이 전 건이라 필터가 사실상 없었다.
        # 이제 추천은 상위 N건만 돌려주므로 그대로 쓰면 일정이 대부분 사라진다.
        saved_ids = repo.saved_policy_ids(user_id)
        today = date.today()
        visible = []
        for event in rows:
            kind = (event.get("event_type") or "").upper()
            if kind == "POLICY":
                due = event.get("due_date")
                if event.get("policy_id") not in saved_ids and not (due and due >= today):
                    continue
            if kind == "USER" and event.get("user_id") != user_id:
                continue
            visible.append(event)
        rows = visible
    if year:
        rows = [e for e in rows if e.get("due_date") and e["due_date"].year == year]
    if month:
        rows = [e for e in rows if e.get("due_date") and e["due_date"].month == month]
    rows.sort(key=lambda e: e.get("due_date") or date.max)
    return [_to_item(e, user_id) for e in rows]


def create_personal_event(
    user_id: int,
    title: str,
    due_date: date,
    description: str = "",
    remind: bool = True,
    notify_at: datetime | None = None,
) -> dict:
    eid = repo.insert_event(
        "USER",
        title.strip(),
        due_date,
        (description or "").strip(),
        user_id=user_id,
    )
    if remind:
        when = notify_at or datetime.combine(due_date, datetime.min.time()).replace(hour=9)
        create_reminder(user_id, eid, when)
    event = repo.get_event(eid)
    return _to_item(event, user_id)


def delete_personal_event(user_id: int, event_id: int) -> None:
    event = repo.get_event(event_id)
    if not event or event.get("event_type") != "USER" or event.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="내 일정을 찾을 수 없습니다.")
    repo.delete_event(event_id)


def list_reminders(user_id: int) -> list[dict]:
    items = []
    for reminder in repo.list_reminders(user_id):
        event = repo.get_event(reminder["event_id"])
        if not event:
            continue
        due = event["due_date"]
        notify_at = reminder["notify_at"]
        items.append(
            {
                "reminderId": reminder["id"],
                "eventId": reminder["event_id"],
                "title": event["title"],
                "dueDate": due,
                "notifyAt": notify_at,
                "dueSoon": 0 <= (due - date.today()).days <= 3,
                "arrived": notify_at <= datetime.now(),
            }
        )
    return items


def create_reminder(user_id: int, event_id: int, notify_at: datetime) -> int:
    if not repo.get_event(event_id):
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
    rid = repo.upsert_reminder(user_id, event_id, notify_at)
    if notify_at <= datetime.now():
        from services.notify_service import dispatch_due_reminders

        dispatch_due_reminders()
    return rid


def delete_reminder(user_id: int, reminder_id: int) -> None:
    reminder = repo.get_reminder(reminder_id)
    if not reminder or reminder["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="리마인더를 찾을 수 없습니다.")
    repo.delete_reminder(reminder_id)
