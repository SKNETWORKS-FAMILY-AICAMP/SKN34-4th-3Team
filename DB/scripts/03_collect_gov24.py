# =========================================================
# 정부24 "대한민국 공공서비스(혜택) 정보" API 수집 + DB 적재
# 근거: Swagger 실제 응답 확인 완료 (서비스명, 지원대상, 지원내용 등)
# =========================================================

import os
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOV24_API_KEY")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

BASE_URL = "https://api.odcloud.kr/api/gov24/v3/serviceList"

# 서비스명에 이 단어가 포함된 것만 수집
SEARCH_KEYWORDS = ["창업", "청년", "1인", "소상공인", "세액", "융자", "보증", "예비창업", "초기창업"]


def fetch_services(keyword, page=1, per_page=100):
    url = (
        f"{BASE_URL}?page={page}&perPage={per_page}"
        f"&cond[서비스명::LIKE]={keyword}"
        f"&serviceKey={API_KEY}"
    )
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        raise requests.exceptions.HTTPError(
            f"정부24 API 요청 실패 (keyword={keyword}, page={page}, status={response.status_code}) "
        ) from None
    return response.json()


def fetch_all_pages(keyword):
    all_items = []
    page = 1
    while True:
        data = fetch_services(keyword, page=page)
        items = data.get("data", [])
        all_items.extend(items)

        match_count = data.get("matchCount", 0)
        print(f"  [{keyword}] {page}페이지: {len(items)}건 (전체 {match_count}건 중 누적 {len(all_items)}건)")

        if len(all_items) >= match_count or not items:
            break
        page += 1

    return all_items


def map_to_policy_row(item):
    return {
        "title": item.get("서비스명", ""),
        "region": None, 
        "industry": item.get("서비스분야", None),
        "target": item.get("지원대상", None),
        "benefit": item.get("지원내용", None),
        "eligibility_rule": item.get("선정기준", None),
        "source": item.get("상세조회URL", None),
    }


def insert_policies(rows):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    inserted = 0
    for row in rows:
        cur.execute("SELECT 1 FROM policies WHERE title = %s", (row["title"],))
        if cur.fetchone():
            continue 

        cur.execute(
            """
            INSERT INTO policies (title, region, industry, target, benefit, eligibility_rule, source)
            VALUES (%(title)s, %(region)s, %(industry)s, %(target)s, %(benefit)s, %(eligibility_rule)s, %(source)s)
            """,
            row,
        )
        inserted += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"신규 {inserted}건 저장 (중복 {len(rows) - inserted}건은 건너뜀)")


if __name__ == "__main__":
    for keyword in SEARCH_KEYWORDS:
        print(f"[{keyword}] 검색 시작...")
        items = fetch_all_pages(keyword)
        rows = [map_to_policy_row(item) for item in items]
        insert_policies(rows)

    print("전체 수집 완료!")