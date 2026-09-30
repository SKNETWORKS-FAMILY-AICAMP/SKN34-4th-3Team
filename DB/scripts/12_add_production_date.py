# =========================================================
# 국세청 법령해석례 생산일자 보강 스크립트
#
# 이미 tax_documents에 들어간 국세청 법령해석례 content 맨 앞에 생산일자를 추가하는 일회성 UPDATE 스크립트.
#
# 방식: ntstDcmId를 추출해 action.do API를 재호출, 
#       ntstDcmRgtDt만 가져와서 content 앞에 "생산일자: YYYY.MM.DD" 형태로 붙인다.
# =========================================================

import os
import re
import json
import time
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

DETAIL_URL = "https://taxlaw.nts.go.kr/action.do"
REQUEST_DELAY_SECONDS = 1.0

HEADERS = {
    "User-Agent": "SKN34-startup-support-platform-collector (educational project)"
}


def extract_ntst_dcm_id(source_url):
    match = re.search(r"ntstDcmId=(\d+)", source_url or "")
    return match.group(1) if match else None


def fetch_production_date(ntst_dcm_id):
    """action.do API로 생산일자(ntstDcmRgtDt)만 조회."""
    payload = {
        "actionId": "ASIQTB002PR01",
        "paramData": json.dumps({"dcmDVO": {"ntstDcmId": ntst_dcm_id}}, ensure_ascii=False),
    }
    headers = {
        **HEADERS,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    try:
        response = requests.post(DETAIL_URL, data=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        dcm = data.get("data", {}).get("ASIQTB002PR01", {}).get("dcmDVO", {})
        raw_date = dcm.get("ntstDcmRgtDt")
        if raw_date and len(raw_date) == 8:
            return f"{raw_date[:4]}.{raw_date[4:6]}.{raw_date[6:8]}"
        return None
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"    조회 실패 (ntstDcmId={ntst_dcm_id}): {e}")
        return None


if __name__ == "__main__":
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute(
        "SELECT id, source, content FROM tax_documents WHERE law_name = %s",
        ("국세청 법령해석",)
    )
    rows = cur.fetchall()
    cur.close()

    print(f"대상: {len(rows)}건")

    updated = 0
    skipped = 0
    failed = 0

    for i, (doc_id, source, content) in enumerate(rows, 1):
        # 이미 생산일자가 붙어있으면 건너뜀 (재실행 안전성)
        if content and content.startswith("생산일자:"):
            skipped += 1
            continue

        ntst_dcm_id = extract_ntst_dcm_id(source)
        if not ntst_dcm_id:
            print(f"  [{i}/{len(rows)}] id={doc_id}: ntstDcmId 추출 실패")
            failed += 1
            continue

        production_date = fetch_production_date(ntst_dcm_id)
        if not production_date:
            failed += 1
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        new_content = f"생산일자: {production_date}\n\n{content}"

        cur = conn.cursor()
        cur.execute(
            "UPDATE tax_documents SET content = %s WHERE id = %s",
            (new_content, doc_id)
        )
        cur.close()
        updated += 1

        if updated % 20 == 0:
            conn.commit()
            print(f"  [{i}/{len(rows)}] 처리 중, 누적 업데이트 {updated}건 (중간 커밋)")

        time.sleep(REQUEST_DELAY_SECONDS)

    conn.commit()
    conn.close()

    print()
    print("=== 완료 ===")
    print(f"업데이트: {updated}건")
    print(f"건너뜀(이미 처리됨): {skipped}건")
    print(f"실패: {failed}건")
