"""Entity queries used by services. Row-level only — no TRUNCATE."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from core import db


def get_user(user_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))


def get_user_by_email(email: str) -> dict | None:
    return db.fetchone("SELECT * FROM users WHERE email = ?", (email,))


def create_user(email: str, password_hash: str, name: str) -> int:
    return db.insert(
        "INSERT INTO users(email,password_hash,name,age,region,phone,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (email, password_hash, name, None, None, "", "active", db._iso(datetime.now())),
    )


def update_user(user_id: int, fields: dict) -> None:
    mapping = {
        "name": "name",
        "age": "age",
        "region": "region",
        "phone": "phone",
        "status": "status",
    }
    sets = []
    params: list = []
    for src, column in mapping.items():
        if src in fields and fields[src] is not None:
            sets.append(f"{column} = ?")
            params.append(fields[src])
    if not sets:
        return
    params.append(user_id)
    db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", tuple(params))


def list_users(offset: int = 0, limit: int = 20) -> list[dict]:
    return db.fetchall("SELECT * FROM users ORDER BY id LIMIT ? OFFSET ?", (limit, offset))


def get_admin(admin_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM admin_users WHERE id = ?", (admin_id,))


def get_admin_by_email(email: str) -> dict | None:
    return db.fetchone("SELECT * FROM admin_users WHERE email = ?", (email,))


def get_profile(user_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,))


def upsert_profile(user_id: int, payload: dict) -> None:
    current = get_profile(user_id) or {
        "user_id": user_id,
        "business_type": None,
        "industry": None,
        "business_registered_at": None,
        "founded_at": None,
    }
    mapping = {
        "businessType": "business_type",
        "industry": "industry",
        "businessRegisteredAt": "business_registered_at",
        "foundedAt": "founded_at",
    }
    for src, dest in mapping.items():
        if payload.get(src) is not None:
            current[dest] = payload[src]
    if get_profile(user_id):
        db.execute(
            "UPDATE business_profiles SET business_type=?, industry=?, business_registered_at=?, founded_at=? WHERE user_id=?",
            (
                current.get("business_type"),
                current.get("industry"),
                db._iso(current.get("business_registered_at")),
                db._iso(current.get("founded_at")),
                user_id,
            ),
        )
        return
    db.insert(
        "INSERT INTO business_profiles(user_id,business_type,industry,business_registered_at,founded_at) VALUES (?,?,?,?,?)",
        (
            user_id,
            current.get("business_type"),
            current.get("industry"),
            db._iso(current.get("business_registered_at")),
            db._iso(current.get("founded_at")),
        ),
    )


def get_tax_info(user_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM tax_info WHERE user_id = ?", (user_id,))


def upsert_tax_info(user_id: int, tax_type: str, details: str) -> None:
    now = db._iso(datetime.now())
    if get_tax_info(user_id):
        db.execute(
            "UPDATE tax_info SET tax_type=?, details=?, updated_at=? WHERE user_id=?",
            (tax_type, details, now, user_id),
        )
        return
    db.insert(
        "INSERT INTO tax_info(user_id,tax_type,details,updated_at) VALUES (?,?,?,?)",
        (user_id, tax_type, details, now),
    )


def insert_tax_reduction(user_id: int, eligible: bool, reasons: list, legal_basis: str) -> None:
    db.insert(
        "INSERT INTO tax_reduction_results(user_id,eligible,reasons,legal_basis,judged_at) VALUES (?,?,?,?,?)",
        (user_id, bool(eligible), db.dumps(reasons), legal_basis, db._iso(datetime.now())),
    )


def latest_tax_reduction(user_id: int) -> dict | None:
    return db.fetchone(
        "SELECT * FROM tax_reduction_results WHERE user_id = ? ORDER BY judged_at DESC, id DESC LIMIT 1",
        (user_id,),
    )


def insert_chat(
    user_id: int, category: str, question: str, answer: str, sources: list[dict], room_id: int
) -> int:
    mid = db.insert(
        "INSERT INTO chat_messages(user_id,category,room_id,question,answer,created_at) VALUES (?,?,?,?,?,?)",
        (user_id, category, room_id, question, answer, db._iso(datetime.now())),
    )
    for item in sources:
        db.insert(
            "INSERT INTO answer_sources(message_id,title,url,excerpt) VALUES (?,?,?,?)",
            (mid, item.get("title"), item.get("url"), item.get("excerpt")),
        )
    return mid


def get_chat(message_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM chat_messages WHERE id = ?", (message_id,))


def chat_sources(message_id: int) -> list[dict]:
    return db.fetchall("SELECT title, url, excerpt FROM answer_sources WHERE message_id = ?", (message_id,))


def list_chats(user_id: int, category: str | None = None) -> list[dict]:
    """사용자에게 보여줄 기록. 삭제한 방의 메시지는 뺀다."""
    sql = (
        "SELECT m.* FROM chat_messages m JOIN chat_rooms r ON r.id = m.room_id "
        "WHERE m.user_id = ? AND r.deleted_at IS NULL"
    )
    params: tuple = (user_id,)
    if category:
        sql += " AND m.category = ?"
        params += (category,)
    return db.fetchall(sql + " ORDER BY m.created_at, m.id", params)


def count_chats(user_id: int) -> int:
    """관리자 통계용. 삭제한 방의 메시지까지 센다."""
    return int(db.scalar("SELECT COUNT(*) FROM chat_messages WHERE user_id = ?", (user_id,)) or 0)


def recent_chats(user_id: int, category: str, room_id: int, limit: int = 10) -> list[dict]:
    """LLM에 보낼 대화 문맥용 최근 기록. 같은 사용자·카테고리·대화방 행만 시간순으로 돌려준다."""
    rows = db.fetchall(
        "SELECT * FROM chat_messages WHERE user_id = ? AND category = ? AND room_id = ? "
        "ORDER BY created_at DESC, id DESC LIMIT ?",
        (user_id, category, room_id, limit),
    )
    return list(reversed(rows))


def list_rooms(user_id: int, category: str) -> list[dict]:
    """활성 대화방 목록. 제목이 없을 때 보여줄 첫 질문을 함께 돌려준다."""
    return db.fetchall(
        "SELECT r.*, (SELECT m.question FROM chat_messages m WHERE m.room_id = r.id "
        "ORDER BY m.id LIMIT 1) AS first_question "
        "FROM chat_rooms r WHERE r.user_id = ? AND r.category = ? AND r.deleted_at IS NULL "
        "ORDER BY r.updated_at DESC, r.id DESC",
        (user_id, category),
    )


def create_room(user_id: int, category: str) -> int:
    now = db._iso(datetime.now())
    return db.insert(
        "INSERT INTO chat_rooms(user_id,category,created_at,updated_at) VALUES (?,?,?,?)",
        (user_id, category, now, now),
    )


def get_room(room_id: int, user_id: int) -> dict | None:
    """본인 소유의 활성 방만 돌려준다."""
    return db.fetchone(
        "SELECT * FROM chat_rooms WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (room_id, user_id),
    )


def rename_room(room_id: int, user_id: int, title: str | None) -> None:
    db.execute(
        "UPDATE chat_rooms SET title = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (title, room_id, user_id),
    )


def touch_room(room_id: int) -> None:
    db.execute("UPDATE chat_rooms SET updated_at = now() WHERE id = ?", (room_id,))


def delete_room(room_id: int, user_id: int) -> None:
    db.execute(
        "UPDATE chat_rooms SET deleted_at = now() WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (room_id, user_id),
    )


def delete_rooms(user_id: int, category: str | None = None) -> int:
    """사용자의 대화방을 삭제 표시한다. 메시지 행은 통계용으로 남는다."""
    sql = "SELECT id FROM chat_rooms WHERE user_id = ? AND deleted_at IS NULL"
    params: tuple = (user_id,)
    if category:
        sql += " AND category = ?"
        params += (category,)
    rooms = db.fetchall(sql, params)
    for room in rooms:
        delete_room(room["id"], user_id)
    return len(rooms)


def list_events() -> list[dict]:
    return db.fetchall("SELECT * FROM calendar_events")


def get_event(event_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM calendar_events WHERE id = ?", (event_id,))


def insert_event(
    event_type: str,
    title: str,
    due_date: date | str,
    description: str = "",
    *,
    business_type: str | None = None,
    policy_id: int | None = None,
    user_id: int | None = None,
) -> int:
    return db.insert(
        "INSERT INTO calendar_events(event_type,business_type,policy_id,user_id,title,due_date,description) VALUES (?,?,?,?,?,?,?)",
        (event_type, business_type, policy_id, user_id, title, db._iso(due_date), description),
    )


def delete_event(event_id: int) -> None:
    db.execute("DELETE FROM reminders WHERE event_id = ?", (event_id,))
    db.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))


def list_reminders(user_id: int) -> list[dict]:
    return db.fetchall("SELECT * FROM reminders WHERE user_id = ?", (user_id,))


def get_reminder(reminder_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM reminders WHERE id = ?", (reminder_id,))


def get_reminder_for_event(user_id: int, event_id: int) -> dict | None:
    return db.fetchone(
        "SELECT * FROM reminders WHERE user_id = ? AND event_id = ?",
        (user_id, event_id),
    )


def upsert_reminder(user_id: int, event_id: int, notify_at: datetime) -> int:
    existing = get_reminder_for_event(user_id, event_id)
    if existing:
        db.execute(
            "UPDATE reminders SET notify_at=?, dispatched=? WHERE id=?",
            (db._iso(notify_at), False, existing["id"]),
        )
        return existing["id"]
    return db.insert(
        "INSERT INTO reminders(user_id,event_id,notify_at,created_at,dispatched) VALUES (?,?,?,?,?)",
        (user_id, event_id, db._iso(notify_at), db._iso(datetime.now()), False),
    )


def delete_reminder(reminder_id: int) -> None:
    db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))


def due_reminders() -> list[dict]:
    return db.fetchall("SELECT * FROM reminders WHERE dispatched = ?", (False,))


def mark_reminder_dispatched(reminder_id: int) -> None:
    db.execute("UPDATE reminders SET dispatched = ? WHERE id = ?", (True, reminder_id))


def saved_policy_ids(user_id: int) -> set[int]:
    rows = db.fetchall("SELECT policy_id FROM saved_policies WHERE user_id = ?", (user_id,))
    return {row["policy_id"] for row in rows}


def list_notifications(user_id: int) -> list[dict]:
    return db.fetchall(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )


def unread_count(user_id: int) -> int:
    return int(
        db.scalar(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_flag = ?",
            (user_id, False),
        )
        or 0
    )


def mark_notifications_read(user_id: int, notification_id: int | None = None) -> None:
    if notification_id is None:
        db.execute(
            "UPDATE notifications SET read_flag = ? WHERE user_id = ?",
            (True, user_id),
        )
        return
    db.execute(
        "UPDATE notifications SET read_flag = ? WHERE user_id = ? AND id = ?",
        (True, user_id, notification_id),
    )


def insert_notification(user_id: int, kind: str, title: str, body: str, channel: str, status: str = "delivered") -> int:
    return db.insert(
        "INSERT INTO notifications(user_id,kind,title,body,channel,status,read_flag,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, kind, title, body, channel, status, False, db._iso(datetime.now())),
    )


def insert_receipt(
    user_id: int,
    filename: str,
    *,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
) -> int:
    return db.insert(
        "INSERT INTO receipts(user_id,image_url,status,created_at,image_data,mime_type) VALUES (?,?,?,?,?,?)",
        # 서버 시간대와 무관하게 UTC로 저장한다. 읽는 쪽(expense_service)이 UTC로 표시해 브라우저가 현지 시각으로 바꾼다.
        (user_id, filename, "done", db._iso(datetime.now(timezone.utc).replace(tzinfo=None)), image_bytes, mime_type),
    )


def get_receipt_meta(receipt_id: int) -> dict | None:
    return db.fetchone("SELECT id, user_id, created_at FROM receipts WHERE id = ?", (receipt_id,))


def get_receipt_image(receipt_id: int) -> dict | None:
    return db.fetchone(
        "SELECT id, user_id, image_data, mime_type FROM receipts WHERE id = ?", (receipt_id,)
    )


def insert_extraction(
    receipt_id: int,
    spent,
    vendor: str,
    amount: int,
    items: list,
    proof_type: str = "unknown",
    read_meta: dict | None = None,
) -> int:
    return db.insert(
        "INSERT INTO receipt_extractions(receipt_id,date,vendor,amount,items,proof_type,read_meta) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            receipt_id,
            db._iso(spent),
            vendor,
            amount,
            db.dumps(items),
            proof_type,
            json.dumps(read_meta, ensure_ascii=False) if read_meta else None,
        ),
    )


def insert_expense(
    receipt_id: int,
    user_id: int,
    category: str,
    amount: int,
    spent,
    deductible: bool,
    confidence: float,
    basis: str,
    tier: str,
    proof_valid: bool | None,
    missing_fields: list,
) -> int:
    return db.insert(
        "INSERT INTO expenses(receipt_id,user_id,category,amount,date,deductible,"
        "deductible_confidence,deductible_basis,deductible_tier,proof_valid,missing_fields) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            receipt_id,
            user_id,
            category,
            amount,
            db._iso(spent),
            bool(deductible),
            confidence,
            basis,
            tier,
            None if proof_valid is None else bool(proof_valid),
            db.dumps(missing_fields),
        ),
    )


def get_receipt(receipt_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM receipts WHERE id = ?", (receipt_id,))


def get_extraction(receipt_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM receipt_extractions WHERE receipt_id = ?", (receipt_id,))


def get_expense(expense_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM expenses WHERE id = ?", (expense_id,))


def list_expenses(user_id: int) -> list[dict]:
    return db.fetchall("SELECT * FROM expenses WHERE user_id = ?", (user_id,))


def update_expense(
    expense_id: int,
    category: str,
    deductible: bool,
    confidence: float,
    basis: str,
    tier: str,
    proof_valid: bool | None,
    missing_fields: list,
) -> None:
    db.execute(
        "UPDATE expenses SET category=?, deductible=?, deductible_confidence=?, deductible_basis=?, "
        "deductible_tier=?, proof_valid=?, missing_fields=? WHERE id=?",
        (
            category,
            bool(deductible),
            confidence,
            basis,
            tier,
            None if proof_valid is None else bool(proof_valid),
            db.dumps(missing_fields),
            expense_id,
        ),
    )


def delete_expense(expense_id: int, receipt_id: int) -> None:
    db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    leftover = db.scalar("SELECT COUNT(*) FROM expenses WHERE receipt_id = ?", (receipt_id,))
    if int(leftover or 0) == 0:
        db.execute("DELETE FROM receipt_extractions WHERE receipt_id = ?", (receipt_id,))
        db.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))


def list_policies(offset: int = 0, limit: int = 20) -> list[dict]:
    return db.fetchall(
        "SELECT * FROM policies ORDER BY id LIMIT ? OFFSET ?", (limit, offset)
    )


def search_policies(
    keyword: str | None = None,
    region: str | None = None,
    industry: str | None = None,
    only_announcements: bool = False,
) -> list[dict]:
    """필터에 맞는 정책 전체. 정렬이 점수 기반이라 여기서는 자르지 않는다.

    와일드카드는 SQL이 아니라 파라미터 값에 넣는다. `db._adapt`가 Postgres에서
    `?`를 `%s`로 바꾸므로 SQL 안의 리터럴 `%`는 psycopg가 포맷 문자로 해석한다.
    """
    where: list[str] = []
    params: list = []
    if only_announcements:
        where.append("EXISTS (SELECT 1 FROM announcements a WHERE a.policy_id = policies.id)")
    if keyword:
        where.append("(title LIKE ? OR benefit LIKE ? OR source LIKE ? OR industry LIKE ? OR region LIKE ?)")
        params += [f"%{keyword}%"] * 5
    if region:
        # 수집 단계에서 17개 시·도로 정규화하므로 부분 일치가 필요 없다.
        # '전국'은 지역 조건과 무관하게 모두에게 해당한다.
        where.append("(region = ? OR region = ? OR region IS NULL)")
        params += [region, "전국"]
    if industry:
        where.append("(industry LIKE ? OR industry = ? OR industry IS NULL)")
        params += [f"%{industry}%", "전 업종"]
    sql = "SELECT * FROM policies"
    if where:
        sql += " WHERE " + " AND ".join(where)
    return db.fetchall(sql, tuple(params))


def get_policy(policy_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM policies WHERE id = ?", (policy_id,))


def announcement_of(policy_id: int) -> dict | None:
    return db.fetchone(
        "SELECT * FROM announcements WHERE policy_id = ? ORDER BY id DESC LIMIT 1",
        (policy_id,),
    )


def announcement_map() -> dict[int, dict]:
    mapped: dict[int, dict] = {}
    for row in db.fetchall("SELECT * FROM announcements ORDER BY id"):
        pid = row.get("policy_id")
        if pid is not None:
            mapped[pid] = row
    return mapped


def get_announcement(announcement_id: int) -> dict | None:
    return db.fetchone("SELECT * FROM announcements WHERE id = ?", (announcement_id,))


def get_summary(announcement_id: int) -> dict | None:
    return db.fetchone(
        "SELECT * FROM announcement_summaries WHERE announcement_id = ?",
        (announcement_id,),
    )


def upsert_summary(announcement_id: int, summary: dict) -> None:
    if get_summary(announcement_id):
        db.execute(
            "UPDATE announcement_summaries SET target=?, benefit=?, period=?, documents=?, notes=?, source=?, llm_used=? WHERE announcement_id=?",
            (
                summary.get("target"),
                summary.get("benefit"),
                summary.get("period"),
                summary.get("documents"),
                summary.get("notes"),
                summary.get("source"),
                bool(summary.get("llm_used")),
                announcement_id,
            ),
        )
        return
    db.insert(
        "INSERT INTO announcement_summaries(announcement_id,target,benefit,period,documents,notes,source,llm_used) VALUES (?,?,?,?,?,?,?,?)",
        (
            announcement_id,
            summary.get("target"),
            summary.get("benefit"),
            summary.get("period"),
            summary.get("documents"),
            summary.get("notes"),
            summary.get("source"),
            bool(summary.get("llm_used")),
        ),
    )


def save_policy(user_id: int, policy_id: int) -> None:
    existing = db.fetchone(
        "SELECT id FROM saved_policies WHERE user_id = ? AND policy_id = ?",
        (user_id, policy_id),
    )
    if existing:
        return
    db.insert(
        "INSERT INTO saved_policies(user_id,policy_id,saved_at) VALUES (?,?,?)",
        (user_id, policy_id, db._iso(datetime.now())),
    )


def unsave_policy(user_id: int, policy_id: int) -> None:
    db.execute(
        "DELETE FROM saved_policies WHERE user_id = ? AND policy_id = ?",
        (user_id, policy_id),
    )


def insert_policy(admin_id: int, body: dict) -> int:
    return db.insert(
        "INSERT INTO policies(admin_id,title,region,industry,target,benefit,eligibility_rule,source,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            admin_id,
            body.get("title") or "제목 없음",
            body.get("region") or "전국",
            body.get("industry") or "전 업종",
            body.get("target") or "",
            body.get("benefit") or body.get("content") or "",
            body.get("eligibilityRule") or "",
            body.get("source") or "",
            db._iso(datetime.now()),
        ),
    )


def insert_announcement(policy_id: int | None, body: dict, start, end) -> int:
    return db.insert(
        "INSERT INTO announcements(policy_id,raw_content,source_url,apply_start_date,apply_end_date,apply_method,created_at) VALUES (?,?,?,?,?,?,?)",
        (
            policy_id,
            body.get("content") or body.get("benefit") or body.get("title") or "",
            body.get("sourceUrl") or body.get("source") or "",
            db._iso(start),
            db._iso(end),
            body.get("applyMethod") or "",
            db._iso(datetime.now()),
        ),
    )


def list_announcements(offset: int = 0, limit: int = 20) -> list[dict]:
    return db.fetchall(
        "SELECT * FROM announcements ORDER BY id LIMIT ? OFFSET ?", (limit, offset)
    )


def open_announcements(limit: int = 20) -> list[dict]:
    """마감이 지나지 않은 공고. 마감 임박순.

    LLM `/rag/chat`의 noticeResults와 `GET /announcements`가 함께 쓴다.
    제목·지역·업종은 announcements에 없어 policies에서 가져온다. policy_id가 없는
    공고는 제목을 만들 수 없고 LLM이 빈 제목을 422로 거부하므로 JOIN으로 걸러진다.
    """
    return db.fetchall(
        "SELECT a.id, a.policy_id, p.title, p.region, p.industry, p.target, p.benefit,"
        " a.raw_content, a.source_url, a.apply_start_date, a.apply_end_date"
        " FROM announcements a JOIN policies p ON a.policy_id = p.id"
        " WHERE a.apply_end_date IS NOT NULL AND a.apply_end_date >= CURRENT_DATE"
        " ORDER BY a.apply_end_date, a.id LIMIT ?",
        (limit,),
    )


def count_open_announcements() -> int:
    return int(
        db.scalar(
            "SELECT COUNT(*) FROM announcements"
            " WHERE apply_end_date IS NOT NULL AND apply_end_date >= CURRENT_DATE"
        )
        or 0
    )


def list_tax_documents() -> list[dict]:
    return db.fetchall("SELECT * FROM tax_documents")


def insert_tax_document(admin_id: int, body: dict) -> int:
    return db.insert(
        "INSERT INTO tax_documents(admin_id,title,law_name,content,source,created_at) VALUES (?,?,?,?,?,?)",
        (
            admin_id,
            body.get("title"),
            body.get("lawName"),
            body.get("content"),
            body.get("source"),
            db._iso(datetime.now()),
        ),
    )


def count(table: str) -> int:
    return int(db.scalar(f"SELECT COUNT(*) FROM {table}") or 0)


def count_users_by_status(status: str) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM users WHERE COALESCE(status,'active') = ?", (status,)) or 0)
