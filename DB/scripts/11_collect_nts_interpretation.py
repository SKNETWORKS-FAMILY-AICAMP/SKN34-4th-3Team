# =========================================================
# 국세청 법령해석례 수집 스크립트
#
#   - 진행 상황 로그를 "처리 건수" 기준으로도 찍도록 개선함
#     (신규 저장 건수만 기준으로 하면 대부분 중복일 때 로그가
#      한참 안 찍혀서 멈춘 것처럼 보이는 문제가 있었음, 2026-09-24)
# =========================================================

import os
import re
import json
import time
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

OC = os.getenv("LAW_API_KEY")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

LIST_URL = "http://www.law.go.kr/DRF/lawSearch.do"
DETAIL_URL = "https://taxlaw.nts.go.kr/action.do"

KEYWORDS = ["창업", "벤처기업", "세액감면", "감면세액"]

REQUEST_DELAY_SECONDS = 1.0
PROGRESS_LOG_EVERY = 50  # 처리 건수 기준 로그 주기

HEADERS = {
    "User-Agent": "SKN34-startup-support-platform-collector (educational project)"
}


def fetch_list(keyword, page=1, display=100):
    params = {
        "OC": OC,
        "target": "ntsCgmExpc",
        "type": "JSON",
        "query": keyword,
        "display": display,
        "page": page,
    }
    response = requests.get(LIST_URL, params=params, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def fetch_all_list(keyword):
    all_items = []
    page = 1
    while True:
        data = fetch_list(keyword, page=page)
        body = data.get("CgmExpc", {})
        items = body.get("cgmExpc", [])
        if isinstance(items, dict):
            items = [items]
        total_cnt = int(body.get("totalCnt", 0))

        all_items.extend(items)
        print(f"  [{keyword}] {page}페이지: {len(items)}건 (전체 {total_cnt}건 중 누적 {len(all_items)}건)")

        if len(all_items) >= total_cnt or not items:
            break
        page += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    return all_items


def extract_ntst_dcm_id(detail_link):
    match = re.search(r"ntstDcmId=(\d+)", detail_link or "")
    return match.group(1) if match else None


def fetch_detail(ntst_dcm_id):
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
        return data.get("data", {}).get("ASIQTB002PR01", {}).get("dcmDVO", {})
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"    본문 조회 실패 (ntstDcmId={ntst_dcm_id}): {e}")
        return None


def build_content(dcm):
    parts = []

    raw_date = dcm.get("ntstDcmRgtDt")
    if raw_date and len(raw_date) == 8:
        formatted_date = f"{raw_date[:4]}.{raw_date[4:6]}.{raw_date[6:8]}"
        parts.append(f"생산일자: {formatted_date}")

    gist = dcm.get("ntstDcmGistCntn")
    reply = dcm.get("ntstDcmCntn")

    if gist:
        parts.append(f"요지: {gist}")
    if reply:
        parts.append(f"회신: {reply}")

    return "\n\n".join(parts) if parts else None


def is_already_saved(conn, full_title):
    """title 중복 여부만 빠르게 확인 (본문 API 호출 전에 먼저 체크해서 불필요한 API 호출을 줄임)."""
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM tax_documents WHERE title = %s", (full_title,))
    exists = cur.fetchone() is not None
    cur.close()
    return exists


def insert_interpretation(conn, item, dcm):
    cur = conn.cursor()

    title = item.get("안건명", "") or dcm.get("ntstDcmTtl", "")
    case_no = item.get("안건번호", "")
    full_title = f"[국세청 법령해석] {title} ({case_no})" if case_no else f"[국세청 법령해석] {title}"

    content = build_content(dcm)
    if not content:
        cur.close()
        return False

    cur.execute(
        """
        INSERT INTO tax_documents (title, law_name, content, source)
        VALUES (%(title)s, %(law_name)s, %(content)s, %(source)s)
        """,
        {
            "title": full_title,
            "law_name": "국세청 법령해석",
            "content": content,
            "source": item.get("법령해석상세링크", ""),
        },
    )
    cur.close()
    return True


if __name__ == "__main__":
    conn = psycopg2.connect(**DB_CONFIG)
    total_inserted = 0
    total_skipped = 0
    total_failed = 0
    total_processed = 0

    seen_ids = set()

    for keyword in KEYWORDS:
        print(f"\n=== [{keyword}] 목록 수집 시작 ===")
        items = fetch_all_list(keyword)

        print(f"=== [{keyword}] 본문 조회 시작 ({len(items)}건) ===")
        for i, item in enumerate(items, 1):
            link = item.get("법령해석상세링크", "")
            ntst_dcm_id = extract_ntst_dcm_id(link)
            if not ntst_dcm_id or ntst_dcm_id in seen_ids:
                total_skipped += 1
                total_processed += 1
                continue
            seen_ids.add(ntst_dcm_id)

            # title 중복 체크를 먼저 해서, 이미 있는 건 API 호출 자체를 건너뜀
            title = item.get("안건명", "")
            case_no = item.get("안건번호", "")
            full_title = f"[국세청 법령해석] {title} ({case_no})" if case_no else f"[국세청 법령해석] {title}"
            if is_already_saved(conn, full_title):
                total_skipped += 1
                total_processed += 1
                if total_processed % PROGRESS_LOG_EVERY == 0:
                    print(f"  [{keyword}] {i}/{len(items)}건 처리 (누적 처리 {total_processed}, 저장 {total_inserted}, 건너뜀 {total_skipped})")
                continue

            dcm = fetch_detail(ntst_dcm_id)
            total_processed += 1
            if dcm is None:
                total_failed += 1
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            if insert_interpretation(conn, item, dcm):
                total_inserted += 1
                conn.commit()
            else:
                total_skipped += 1

            if total_processed % PROGRESS_LOG_EVERY == 0:
                print(f"  [{keyword}] {i}/{len(items)}건 처리 (누적 처리 {total_processed}, 저장 {total_inserted}, 건너뜀 {total_skipped})")

            time.sleep(REQUEST_DELAY_SECONDS)

        conn.commit()

    conn.close()

    print()
    print("=== 전체 완료 ===")
    print(f"신규 저장: {total_inserted}건")
    print(f"건너뜀(중복/내용없음): {total_skipped}건")
    print(f"실패: {total_failed}건")