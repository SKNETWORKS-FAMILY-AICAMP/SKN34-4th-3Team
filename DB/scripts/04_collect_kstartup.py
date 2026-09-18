# =========================================================
# 창업진흥원 K-Startup "지원사업 공고 정보" API 수집 + DB 적재
# 근거: 실제 Swagger 실행 결과 확인 완료
#
# ✏️ 이 API의 공고 하나하나를 policies에도 새로 등록하고,
#    동시에 announcements로 연결합니다.
#    (기존 정부24 데이터의 policies와 자동 매칭은 하지 않음 — 근거 불충분)
# =========================================================

import os
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
 
BASE_URL = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"
 
 
def fetch_announcements(page=1, per_page=100):
    url = (
        f"{BASE_URL}?page={page}&perPage={per_page}"
        f"&cond[rcrt_prgs_yn::EQ]=Y"
        f"&cond[biz_trgt_age::LIKE]=만 20세 이상 ~ 만 39세 이하"
        f"&returnType=json"
        f"&serviceKey={API_KEY}"
    )
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        raise requests.exceptions.HTTPError(
            f"K-Startup API 요청 실패 (page={page}, status={response.status_code}) "
        ) from None
    return response.json()
 
 
def fetch_all_pages():
    all_items = []
    page = 1
    while True:
        data = fetch_announcements(page=page)
        items = data.get("data", [])
        all_items.extend(items)
 
        match_count = data.get("matchCount", 0)
        print(f"  {page}페이지: {len(items)}건 (전체 {match_count}건 중 누적 {len(all_items)}건)")
 
        if len(all_items) >= match_count or not items:
            break
        page += 1
 
    return all_items
 
 
def parse_date(date_str):
    if not date_str or len(date_str) != 8:
        return None
    try:
        return datetime.strptime(date_str, "%Y%m%d").date()
    except ValueError:
        return None
 
 
def insert_policy_and_announcement(conn, item):
    cur = conn.cursor()
 
    title = item.get("biz_pbanc_nm", "")
 
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
                "region": normalize_region(item.get("supt_regin", None)),
                "industry": item.get("supt_biz_clsfc", None),
                "target": item.get("aply_trgt_ctnt", None),
                "benefit": item.get("pbanc_ctnt", None),
                "eligibility_rule": item.get("aply_trgt", None),
                "source": item.get("detl_pg_url", None),
            },
        )
        policy_id = cur.fetchone()[0]
 
    source_url = item.get("detl_pg_url", None)
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
            "raw_content": item.get("pbanc_ctnt", None),
            "source_url": source_url,
            "apply_start_date": parse_date(item.get("pbanc_rcpt_bgng_dt")),
            "apply_end_date": parse_date(item.get("pbanc_rcpt_end_dt")),
        },
    )
    cur.close()
    return True
 
 
if __name__ == "__main__":
    print("K-Startup 지원사업 공고 수집 시작...")
    items = fetch_all_pages()
 
    conn = psycopg2.connect(**DB_CONFIG)
    inserted = 0
    for item in items:
        if insert_policy_and_announcement(conn, item):
            inserted += 1
    conn.commit()
    conn.close()
 
    print(f"신규 announcements {inserted}건 저장 (중복 {len(items) - inserted}건은 건너뜀)")
 