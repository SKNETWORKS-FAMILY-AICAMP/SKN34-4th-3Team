# =========================================================
# 창업진흥원 K-Startup "지원사업 공고 정보" API 수집 + DB 적재
# 근거: 실제 Swagger 실행 결과 확인 완료
#
# ✏️ 이 API의 공고 하나하나를 policies에도 새로 등록하고,
#    동시에 announcements로 연결합니다.
#    (기존 정부24 데이터의 policies와 자동 매칭은 하지 않음 — 근거 불충분)
# =========================================================

import os
import sys
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
from normalize_region import normalize_region
from collect_common import exit_code, json_of, record_failure, request
 
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
    return json_of(request("GET", url))
 
 
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
    conn = psycopg2.connect(**DB_CONFIG)
    fetched = 0
    inserted = 0
    page = 1
    # 페이지마다 바로 적재한다. 페이지가 실패하면 기록하고 멈춘다(재시도 시 처음부터, 중복은 건너뜀).
    while True:
        try:
            data = fetch_announcements(page=page)
            items = data.get("data", [])
            fetched += len(items)

            match_count = data.get("matchCount", 0)
            print(f"  {page}페이지: {len(items)}건 (전체 {match_count}건 중 누적 {fetched}건)")

            for item in items:
                if insert_policy_and_announcement(conn, item):
                    inserted += 1
            conn.commit()
        except Exception as e:
            record_failure(conn, f"page={page}", e)
            break

        if fetched >= match_count or not items:
            break
        page += 1
    conn.close()

    print(f"신규 announcements {inserted}건 저장 (조회 {fetched}건 중 나머지는 중복으로 건너뜀)")
    sys.exit(exit_code())
 