"""Row-level SQL access on Postgres. Never TRUNCATE shared tables."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from core.config import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    DATABASE_URL,
    DEMO_EMAIL,
    DEMO_PASSWORD,
)
from core.security import hash_password

logger = logging.getLogger(__name__)

_DATE_KEYS = {
    "due_date",
    "apply_start_date",
    "apply_end_date",
    "founded_at",
    "business_registered_at",
    "date",
}
_DT_KEYS = {
    "created_at",
    "updated_at",
    "notify_at",
    "judged_at",
    "saved_at",
}


def postgres_connect():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        return None
    parsed = urlparse(DATABASE_URL)
    try:
        return psycopg.connect(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 5432,
            user=parsed.username or "admin",
            password=parsed.password or "admin1234",
            dbname=(parsed.path or "/startup_platform").lstrip("/") or "startup_platform",
            connect_timeout=5,
            row_factory=dict_row,
        )
    except Exception:
        return None


def _adapt(sql: str) -> str:
    return sql.replace("?", "%s")


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _parse_date(value):
    if value is None or isinstance(value, date):
        return value
    text = str(value)[:10]
    return date.fromisoformat(text)


def _parse_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _row(item) -> dict:
    data = dict(item)
    for key in _DATE_KEYS:
        if key in data:
            data[key] = _parse_date(data[key]) if data[key] else None
    for key in _DT_KEYS:
        if key in data:
            data[key] = _parse_dt(data[key]) if data[key] else None
    for key in ("eligible", "deductible", "dispatched", "llm_used", "read_flag", "proof_valid"):
        if key in data and data[key] is not None:
            data[key] = bool(data[key])
    if "read_flag" in data:
        data["read"] = bool(data.get("read_flag"))
    if "reasons" in data and isinstance(data["reasons"], str):
        try:
            data["reasons"] = json.loads(data["reasons"] or "[]")
        except json.JSONDecodeError:
            data["reasons"] = []
    if "items" in data and isinstance(data["items"], str):
        try:
            data["items"] = json.loads(data["items"] or "[]")
        except json.JSONDecodeError:
            data["items"] = []
    if "read_meta" in data:
        try:
            data["read_meta"] = json.loads(data["read_meta"]) if data["read_meta"] else {}
        except (TypeError, json.JSONDecodeError):
            data["read_meta"] = {}
    if "missing_fields" in data and isinstance(data["missing_fields"], str):
        try:
            data["missing_fields"] = json.loads(data["missing_fields"] or "[]")
        except json.JSONDecodeError:
            data["missing_fields"] = []
    if "legal_basis" in data and "legalBasis" not in data:
        data["legalBasis"] = data.get("legal_basis")
    return data


@contextmanager
def connection():
    conn = postgres_connect()
    if conn is None:
        raise RuntimeError("Postgres 연결에 실패했습니다.")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetchall(sql: str, params: tuple = ()) -> list[dict]:
    with connection() as conn:
        cur = conn.execute(_adapt(sql), params)
        return [_row(row) for row in cur.fetchall()]


def fetchone(sql: str, params: tuple = ()) -> dict | None:
    rows = fetchall(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> None:
    with connection() as conn:
        conn.execute(_adapt(sql), params)


def insert(sql: str, params: tuple = ()) -> int:
    with connection() as conn:
        query = sql.rstrip().rstrip(";")
        if "RETURNING" not in query.upper():
            query = f"{query} RETURNING id"
        cur = conn.execute(_adapt(query), params)
        row = cur.fetchone()
        return int(dict(row)["id"])


def scalar(sql: str, params: tuple = ()):
    row = fetchone(sql, params)
    if not row:
        return None
    return next(iter(row.values()))


def dumps(value) -> str:
    return json.dumps(value or [], ensure_ascii=False)


def db_path() -> str:
    """진단용 DB 위치. 자격증명은 노출하지 않는다."""
    return masked_database_url()


def masked_database_url() -> str:
    """DATABASE_URL에서 사용자·비밀번호를 지우고 host:port/dbname만 남긴다."""
    try:
        parsed = urlparse(DATABASE_URL)
    except ValueError:
        return "postgres"
    host = parsed.hostname or "unknown"
    port = parsed.port or 5432
    name = (parsed.path or "").lstrip("/") or "unknown"
    return f"{host}:{port}/{name}"


def _apply_extras(conn) -> None:
    path = Path(__file__).resolve().parents[2] / "DB" / "app_extras.sql"
    if not path.is_file():
        return
    # DO $$ 블록이 있어 ;로 나누면 깨진다. 파일 전체를 한 번에 실행한다(전 문장 재실행 안전).
    try:
        conn.execute(path.read_text(encoding="utf-8"))
    except Exception:
        conn.rollback()
        logger.warning("app_extras.sql 적용 실패. psql로 직접 적용 필요", exc_info=True)


def _seed() -> None:
    if not fetchone("SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,)):
        uid = insert(
            "INSERT INTO users(email,password_hash,name,age,region,phone,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                DEMO_EMAIL,
                hash_password(DEMO_PASSWORD),
                "김창업",
                29,
                "서울",
                "",
                "active",
                _iso(datetime.now()),
            ),
        )
        insert(
            "INSERT INTO business_profiles(user_id,business_type,industry,business_registered_at,founded_at) VALUES (?,?,?,?,?)",
            (uid, "간이과세자", "소프트웨어", "2024-03-01", "2024-03-01"),
        )
        insert(
            "INSERT INTO tax_info(user_id,tax_type,details,updated_at) VALUES (?,?,?,?)",
            (uid, "부가가치세", "분기 예정·확정 신고 대상", _iso(datetime.now())),
        )
    if not fetchone("SELECT id FROM admin_users WHERE email = ?", (ADMIN_EMAIL,)):
        insert(
            "INSERT INTO admin_users(email,password_hash,role,created_at) VALUES (?,?,?,?)",
            (ADMIN_EMAIL, hash_password(ADMIN_PASSWORD), "admin", _iso(datetime.now())),
        )
    if int(scalar("SELECT COUNT(*) FROM calendar_events WHERE event_type = ?", ("TAX",)) or 0) == 0:
        tax_dates = [
            ("부가가치세 1기 예정 신고", "2026-04-25", "1~3월분 예정 신고·납부"),
            ("종합소득세 확정 신고", "2026-05-31", "2025년 귀속 종합소득세"),
            ("부가가치세 1기 확정 신고", "2026-07-27", "1~6월분 확정 신고·납부"),
            ("부가가치세 2기 예정 신고", "2026-10-26", "7~9월분 예정 신고·납부"),
            ("원천세 9월분 신고", "2026-10-12", "원천징수세 납부"),
        ]
        for title, due, desc in tax_dates:
            insert(
                "INSERT INTO calendar_events(event_type,business_type,policy_id,title,due_date,description) VALUES (?,?,?,?,?,?)",
                ("TAX", "간이과세자", None, title, due, desc),
            )
    if int(scalar("SELECT COUNT(*) FROM policies") or 0) > 0:
        return
    admin = fetchone("SELECT id FROM admin_users WHERE email = ?", (ADMIN_EMAIL,))
    admin_id = admin["id"] if admin else None
    demo_policies = [
        ("예비창업패키지", "전국", "전 업종", "예비창업자 및 업력 3년 미만 창업자", "사업화 자금 최대 1억원, 멘토링", "age<=39,founded_years<=3", "창업진흥원", "2026-03-01", "2026-03-31", "K-Startup 온라인 신청"),
        ("청년창업사관학교", "서울", "소프트웨어", "만 39세 이하 청년 창업자", "창업 공간, 교육, 사업화 지원금", "age<=39,region=서울", "중소벤처기업부", "2026-04-01", "2026-04-20", "사관학교 홈페이지 접수"),
        ("서울 청년창업 지원금", "서울", "전 업종", "서울 거주 만 39세 이하 1인 창업자", "사업비 최대 2천만원", "age<=39,region=서울", "서울산업진흥원", "2026-09-01", "2026-09-30", "서울기업지원센터 신청"),
        ("소상공인 정책자금", "전국", "도소매", "소상공인 사업자", "저금리 정책자금 대출", "business_type!=미등록", "소상공인시장진흥공단", "2026-01-02", "2026-12-15", "소진공 온라인 신청"),
        ("청년창업 세액감면 안내 사업", "전국", "소프트웨어", "청년 창업 중소기업", "소득세·법인세 감면 상담 및 신청 지원", "age<=39,founded_years<=5", "국세청", "2026-01-01", "2026-12-31", "홈택스 또는 세무서 방문"),
    ]
    for title, region, industry, target, benefit, rule, source, start, end, method in demo_policies:
        pid = insert(
            "INSERT INTO policies(admin_id,title,region,industry,target,benefit,eligibility_rule,source,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (admin_id, title, region, industry, target, benefit, rule, source, _iso(datetime.now())),
        )
        insert(
            "INSERT INTO announcements(policy_id,raw_content,source_url,apply_start_date,apply_end_date,apply_method,created_at) VALUES (?,?,?,?,?,?,?)",
            (
                pid,
                f"{title} 공고문. 신청기간 {start} ~ {end}. {benefit}",
                "https://www.k-startup.go.kr",
                start,
                end,
                method,
                _iso(datetime.now()),
            ),
        )
        insert(
            "INSERT INTO calendar_events(event_type,business_type,policy_id,title,due_date,description) VALUES (?,?,?,?,?,?)",
            ("POLICY", None, pid, f"{title} 신청 마감", end, f"{source} · {region}"),
        )


def init_db() -> str:
    conn = None
    for _ in range(8):
        conn = postgres_connect()
        if conn is not None:
            break
        time.sleep(1.5)
    if conn is None:
        raise RuntimeError("Postgres 연결 실패. DATABASE_URL 확인")
    try:
        _apply_extras(conn)
        conn.commit()
    finally:
        conn.close()
    _seed()
    return "postgres"
