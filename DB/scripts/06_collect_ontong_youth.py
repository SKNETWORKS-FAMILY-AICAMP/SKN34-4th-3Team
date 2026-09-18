# =========================================================
# 온통청년 청년정책 API 수집 + DB 적재 (policies + announcements)
# 근거: 실제 API 응답 확인 완료 (result.youthPolicyList)
# =========================================================

import os
import re
import time
import requests
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
from normalize_region import normalize_region

load_dotenv()

API_KEY = os.getenv("ONTONG_YOUTH_API_KEY")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

BASE_URL = "https://www.youthcenter.go.kr/go/ythip/getPlcy"

KEEP_KEYWORDS_IN_TAG = ["벤처", "중소기업", "대출", "자금", "보증"]

EXCLUDE_KEYWORDS = ["축제", "페스타", "페스티벌", "콘서트", "공연", "체험행사", "챌린지", "장학금", "학자금"]


def fetch_page(page_num=1, page_size=100):
    params = {
        "apiKeyNm": API_KEY,
        "pageNum": page_num,
        "pageSize": page_size,
        "rtnType": "json",
        "lclsfNm": "일자리",
    }
    try:
        response = requests.get(BASE_URL, params=params)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise requests.exceptions.HTTPError(
            f"온통청년 API 요청 실패 (page={page_num}, status={response.status_code}) "
        ) from None
    return response.json()


def fetch_all_pages():
    all_items = []
    page = 1
    while True:
        data = fetch_page(page_num=page)
        result = data.get("result", {})
        items = result.get("youthPolicyList", [])
        tot_count = result.get("pagging", {}).get("totCount", 0)

        all_items.extend(items)
        print(f"  {page}페이지: {len(items)}건 (전체 {tot_count}건 중 누적 {len(all_items)}건)")

        if len(all_items) >= tot_count or not items:
            break
        page += 1
        time.sleep(0.5) 

    return all_items


def is_relevant(item):
    mclsf = item.get("mclsfNm", "") or ""
    kywd = item.get("plcyKywdNm", "") or ""
    name = item.get("plcyNm", "") or ""
    combined = mclsf + kywd + name

    if any(bad in combined for bad in EXCLUDE_KEYWORDS):
        return False

    if mclsf == "창업":
        return True

    if any(kw in kywd for kw in KEEP_KEYWORDS_IN_TAG):
        return True

    return False


def parse_aply_ymd(aply_ymd):
    if not aply_ymd or "~" not in aply_ymd:
        return None, None
    try:
        start_str, end_str = [s.strip() for s in aply_ymd.split("~")]
        start = datetime.strptime(start_str, "%Y%m%d").date()
        end = datetime.strptime(end_str, "%Y%m%d").date()
        return start, end
    except ValueError:
        return None, None


def build_eligibility_rule(item):
    min_age = item.get("sprtTrgtMinAge", "")
    max_age = item.get("sprtTrgtMaxAge", "")
    if min_age and max_age:
        return f"연령 {min_age}~{max_age}세"
    return None


def insert_policy_and_announcement(conn, item):
    cur = conn.cursor()

    title = item.get("plcyNm", "")
    source_url = item.get("refUrlAddr1", None) or None

    region = normalize_region(item.get("rgtrHghrkInstCdNm", None))

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
                "industry": item.get("mclsfNm", None) or None,
                "target": item.get("addAplyQlfcCndCn", None) or None,
                "benefit": item.get("plcySprtCn", None) or None,
                "eligibility_rule": build_eligibility_rule(item),
                "source": source_url,
            },
        )
        policy_id = cur.fetchone()[0]

    start_date, end_date = parse_aply_ymd(item.get("aplyYmd", ""))

    if start_date is None and end_date is None:
        cur.close()
        return False

    cur.execute("SELECT 1 FROM announcements WHERE source_url = %s AND policy_id = %s", (source_url, policy_id))
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
            "raw_content": item.get("plcyExplnCn", None) or None,
            "source_url": source_url,
            "apply_start_date": start_date,
            "apply_end_date": end_date,
        },
    )
    cur.close()
    return True


if __name__ == "__main__":
    print("온통청년 '일자리' 대분류 전체 수집 시작...")
    all_items = fetch_all_pages()

    relevant_items = [item for item in all_items if is_relevant(item)]
    print(f"전체 {len(all_items)}건 중 관련 있는 {len(relevant_items)}건으로 필터링됨")

    conn = psycopg2.connect(**DB_CONFIG)
    inserted = 0
    for item in relevant_items:
        if insert_policy_and_announcement(conn, item):
            inserted += 1
    conn.commit()
    conn.close()

    print(f"announcements 신규 {inserted}건 저장 완료")