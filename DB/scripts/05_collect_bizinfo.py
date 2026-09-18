# =========================================================
# 중소벤처기업부 기업마당 "중소기업 지원사업 공고" API 수집 + DB 적재
# 근거: 실제 Swagger 실행 결과 확인 완료
# =========================================================

import os
import re
import requests
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
from normalize_region import normalize_region

load_dotenv()

API_KEY = os.getenv("GOV24_API_KEY")  

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

BASE_URL = "https://apis.data.go.kr/1421000/bizinfo/pblancBsnsService"


def strip_html(text):
    if not text:
        return text
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_date_range(range_str):
    if not range_str:
        return None, None
    match = re.match(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", range_str)
    if not match:
        return None, None
    try:
        start = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        end = datetime.strptime(match.group(2), "%Y-%m-%d").date()
        return start, end
    except ValueError:
        return None, None


def fetch_page(page_no=1, num_of_rows=100):
    url = (
        f"{BASE_URL}?serviceKey={API_KEY}"
        f"&dataType=json&pageNo={page_no}&numOfRows={num_of_rows}"
    )
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        raise requests.exceptions.HTTPError(
            f"기업마당 API 요청 실패 (page={page_no}, status={response.status_code}) "
        ) from None
    return response.json()


def fetch_all_pages():
    all_items = []
    page = 1
    while True:
        data = fetch_page(page_no=page)
        body = data.get("response", {}).get("body", {})
        items = body.get("items", {}).get("item", [])
        if isinstance(items, dict):  
            items = [items]

        total_count = int(body.get("totalCount", 0))
        all_items.extend(items)
        print(f"  {page}페이지: {len(items)}건 (전체 {total_count}건 중 누적 {len(all_items)}건)")

        if len(all_items) >= total_count or not items:
            break
        page += 1

    return all_items


def insert_policy_and_announcement(conn, item):
    cur = conn.cursor()

    title = item.get("pblancNm", "")
    source_url = item.get("pblancUrl", None)
    benefit = strip_html(item.get("bsnsSumryCn", None))
    start_date, end_date = parse_date_range(item.get("reqstBeginEndDe", None))

    region = normalize_region(item.get("jrsdInsttNm", None))

    cur.execute("SELECT id FROM policies WHERE title = %s", (title,))
    row = cur.fetchone()

    if row:
        policy_id = row[0]
    else:
        cur.execute(
            """
            INSERT INTO policies (title, region, industry, target, benefit, eligibility_rule, source)
            VALUES (%(title)s, %(region)s, %(industry)s, %(target)s, %(benefit)s, %(eligibility_rule)s, %(source)s)
            RETURNING id
            """,
            {
                "title": title,
                "region": region,
                "industry": item.get("pldirSportRealmLclasCodeNm", None),
                "target": item.get("trgetNm", None),
                "benefit": benefit,
                "eligibility_rule": None,
                "source": source_url,
            },
        )
        policy_id = cur.fetchone()[0]

    cur.execute("SELECT 1 FROM announcements WHERE source_url = %s", (source_url,))
    if cur.fetchone():
        cur.close()
        return False

    cur.execute(
        """
        INSERT INTO announcements (policy_id, raw_content, source_url, apply_start_date, apply_end_date)
        VALUES (%(policy_id)s, %(raw_content)s, %(source_url)s, %(apply_start_date)s, %(apply_end_date)s)
        """,
        {
            "policy_id": policy_id,
            "raw_content": benefit,
            "source_url": source_url,
            "apply_start_date": start_date,
            "apply_end_date": end_date,
        },
    )
    cur.close()
    return True


if __name__ == "__main__":
    print("기업마당 지원사업 공고 수집 시작...")
    items = fetch_all_pages()

    conn = psycopg2.connect(**DB_CONFIG)
    inserted = 0
    for item in items:
        if insert_policy_and_announcement(conn, item):
            inserted += 1
    conn.commit()
    conn.close()

    print(f"신규 announcements {inserted}건 저장 (중복 {len(items) - inserted}건은 건너뜀)")