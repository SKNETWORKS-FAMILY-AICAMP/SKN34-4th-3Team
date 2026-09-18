# =========================================================
# 국세기본법 기준 세금 신고기한 자동 계산 + calendar_events 적재
#
# 📄 신고기한 날짜(월/일)는 국세기본법·부가가치세법·소득세법·법인세법에
#    명시된 고정 규칙입니다 (예: 부가세 1기 확정신고 = 매년 7/1~7/25).
# ✏️ "마지막 날이 공휴일이면 다음 평일로 연장"되는 규정을 반영하기 위해
#    holidays 라이브러리로 한국 공휴일을 계산합니다.
#    실행 전 설치 필요: pip install holidays --break-system-packages
#
# 사용법: 매년 초에 이 스크립트를 한 번 실행하면, 그 해의 정확한
#         신고기한이 자동으로 계산되어 DB에 채워집니다.
# =========================================================

import os
import psycopg2
import holidays
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

kr_holidays = holidays.KR()


def adjust_to_business_day(d):
    # 마지막 날이 토/일/공휴일이면 다음 평일로 이동
    while d.weekday() >= 5 or d in kr_holidays:
        d += timedelta(days=1)
    return d


def get_tax_deadlines(year):
    """
    📄 근거: 국세기본법 / 부가가치세법 / 소득세법 / 법인세법의 신고기한 규정
    year: 기준 연도
    """
    raw_deadlines = [
        {
            "title": f"{year}년 1기 부가가치세 확정신고",
            "business_type": "일반사업자",
            "due_date": date(year, 7, 25),
            "description": "1월~6월 사업실적에 대한 부가가치세 확정신고·납부기한",
        },
        {
            "title": f"{year}년 2기 부가가치세 확정신고",
            "business_type": "일반사업자",
            "due_date": date(year, 1, 25),  # 전년도 2기분을 해당 연도 1월에 신고
            "description": "전년도 7월~12월 사업실적에 대한 부가가치세 확정신고·납부기한",
        },
        {
            "title": f"{year}년 종합소득세 확정신고",
            "business_type": "개인사업자",
            "due_date": date(year, 5, 31),
            "description": "전년도 귀속 종합소득세 확정신고·납부기한",
        },
        {
            "title": f"{year}년 부가가치세 예정고지 납부 (1기)",
            "business_type": "일반사업자",
            "due_date": date(year, 4, 25),
            "description": "1기 부가가치세 예정고지분 납부기한 (직전 과세기간 기준 고지)",
        },
        {
            "title": f"{year}년 부가가치세 예정고지 납부 (2기)",
            "business_type": "일반사업자",
            "due_date": date(year, 10, 25),
            "description": "2기 부가가치세 예정고지분 납부기한",
        },
    ]

    # 마지막 날이 공휴일/주말이면 다음 평일로 자동 보정
    for item in raw_deadlines:
        item["due_date"] = adjust_to_business_day(item["due_date"])

    return raw_deadlines


def insert_calendar_events(year):
    deadlines = get_tax_deadlines(year)
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    inserted = 0
    for item in deadlines:
        # 같은 제목+연도의 일정이 이미 있으면 건너뜀 (중복 방지)
        cur.execute(
            "SELECT 1 FROM calendar_events WHERE title = %s AND event_type = 'TAX'",
            (item["title"],),
        )
        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO calendar_events (event_type, business_type, title, due_date, description)
            VALUES ('TAX', %(business_type)s, %(title)s, %(due_date)s, %(description)s)
            """,
            item,
        )
        inserted += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"{year}년 기준 세금 신고 일정 {inserted}건 저장 (중복 {len(deadlines) - inserted}건은 건너뜀)")


if __name__ == "__main__":
    current_year = date.today().year
    # 올해와 내년 일정을 미리 채워둠 (연말에 미리 내년 것도 준비되도록)
    insert_calendar_events(current_year)
    insert_calendar_events(current_year + 1)