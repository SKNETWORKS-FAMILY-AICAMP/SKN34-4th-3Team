# =========================================================
# 기업마당 기존 데이터 region backfill 스크립트
#
# 기존에 region=NULL로 수집된 bizinfo 정책 1,541건의 region을 jrsdInsttNm 필드로 채우는 일회성 스크립트
# 05_collect_bizinfo.py 수정 이후 기존 데이터 정리용 (1회 실행)
# =========================================================

import os
import re
import time
import requests
import psycopg2
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


def get_null_region_policies(conn):
    """DB에서 bizinfo 소스이고 region이 NULL인 정책 목록 조회."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.id, p.title, a.source_url
        FROM policies p
        JOIN announcements a ON a.policy_id = p.id
        WHERE p.source LIKE '%bizinfo%'
          AND p.region IS NULL
          AND a.source_url IS NOT NULL
        ORDER BY p.id
        """
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def extract_pblanc_id(source_url):
    """source_url에서 pblancId 추출."""
    match = re.search(r"pblancId=([A-Z0-9_]+)", source_url)
    return match.group(1) if match else None


def fetch_jrsd_inst_nm(pblanc_id):
    """기업마당 API에서 단건 조회해서 jrsdInsttNm 반환."""
    url = (
        f"{BASE_URL}?serviceKey={API_KEY}"
        f"&dataType=json&pageNo=1&numOfRows=1"
        f"&pblancId={pblanc_id}"
    )
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        body = response.json().get("response", {}).get("body", {})
        items = body.get("items", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        if items:
            return items[0].get("jrsdInsttNm", None)
    except Exception as e:
        print(f"    API 오류 (pblancId={pblanc_id}): {e}")
    return None


def update_region(conn, policy_id, region):
    """policies 테이블의 region 업데이트."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE policies SET region = %s WHERE id = %s",
        (region, policy_id)
    )
    cur.close()


if __name__ == "__main__":
    conn = psycopg2.connect(**DB_CONFIG)

    print("기업마당 region backfill 시작...")
    rows = get_null_region_policies(conn)
    print(f"대상 정책: {len(rows)}건")

    updated = 0
    skipped = 0
    failed = 0

    for i, (policy_id, title, source_url) in enumerate(rows, 1):
        pblanc_id = extract_pblanc_id(source_url)
        if not pblanc_id:
            print(f"  [{i}/{len(rows)}] pblancId 추출 실패: {source_url}")
            failed += 1
            continue

        raw_region = fetch_jrsd_inst_nm(pblanc_id)
        normalized = normalize_region(raw_region)

        if normalized:
            update_region(conn, policy_id, normalized)
            updated += 1
            print(f"  [{i}/{len(rows)}] ✅ {title[:40]}... → {normalized}")
        else:
            skipped += 1
            print(f"  [{i}/{len(rows)}] ⬜ {title[:40]}... → None (중앙부처 등)")

        if i % 10 == 0:
            conn.commit()
            print(f"  --- {i}건 처리 완료, 중간 커밋 ---")

        time.sleep(0.5)

    conn.commit()
    conn.close()

    print()
    print(f"완료!")
    print(f"  UPDATE 성공: {updated}건")
    print(f"  지역 없음(중앙부처 등): {skipped}건")
    print(f"  pblancId 추출 실패: {failed}건")
    print()
    print("결과 확인 쿼리:")
    print("SELECT region, COUNT(*) FROM policies")
    print("WHERE source LIKE '%bizinfo%'")
    print("GROUP BY region ORDER BY count DESC;")