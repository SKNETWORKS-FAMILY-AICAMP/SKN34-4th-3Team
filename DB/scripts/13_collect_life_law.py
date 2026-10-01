# =========================================================
# 생활법령정보(easylaw.go.kr) 크롤링 스크립트 - 본문 수집
#
# 수집 대상:
#   1. 창업(csmAstSeq=6) 카테고리의 전체 업종(26개) 본문
#   2. 사업(csmAstSeq=5) 카테고리 중 "1인 창조기업"(csmSeq=1505),
#      "중소·벤처기업 창업"(csmSeq=632) 본문
# =========================================================

import re
import time
import html
import requests
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

HEADERS = {
    "User-Agent": "SKN34-startup-support-platform-collector (educational project)"
}

REQUEST_DELAY_SECONDS = 1.0

BASE = "https://www.easylaw.go.kr/CSP"

# 창업(csmAstSeq=6) 카드형 업종 26개
STARTUP_CSM_SEQS = {
    "907": "결혼중개업", "1450": "경비", "1765": "귀농인", "1010": "네일샵",
    "633": "동업", "1013": "메이크업샵", "1888": "소상공인 지원", "1009": "미용실",
    "864": "사업자등록", "534": "민박건축", "302": "반찬가게", "716": "세탁소",
    "1973": "소상공인", "2985": "온라인 쇼핑몰", "840": "음식점(2)", "839": "음식점(1)",
    "1971": "지역상권", "1451": "건물 청소", "1453": "체육시설", "706": "커피전문점",
    "2009": "키즈카페", "1967": "펜션", "1966": "푸드트럭", "647": "프랜차이즈",
    "1012": "피부관리실", "1140": "학원",
}

# 사업(csmAstSeq=5) 중 수집 대상 2개
BUSINESS_CSM_SEQS = {
    "1505": "1인 창조기업",
    "632": "중소·벤처기업 창업",
}

ALL_CSM_SEQS = {**STARTUP_CSM_SEQS, **BUSINESS_CSM_SEQS}


def get_chapters(csm_seq):
    """csmSeq 하나의 CsmMain.laf 페이지에서 전체 챕터(ccfNo, cciNo, cnpClsNo) 조합을 추출."""
    url = f"{BASE}/CsmMain.laf"
    params = {"csmSeq": csm_seq}
    response = requests.get(url, params=params, headers=HEADERS, timeout=15)
    text = html.unescape(response.text)

    pattern = re.compile(
        r'CnpClsMain\.laf\?popMenu=ov&csmSeq=' + re.escape(csm_seq) +
        r'&ccfNo=(\d+)&cciNo=(\d+)&cnpClsNo=(\d+)'
    )
    combos = set()
    for m in pattern.finditer(text):
        combos.add((m.group(1), m.group(2), m.group(3)))
    return sorted(combos, key=lambda x: (int(x[0]), int(x[1]), int(x[2])))


def fetch_content(csm_seq, ccf_no, cci_no, cnp_cls_no):
    """콘텐츠 페이지 하나를 크롤링해서 제목과 본문을 추출.
    Returns:
        (title, body) 튜플. 실패하거나 본문 마커를 못 찾으면 (title, None).
    """
    url = f"{BASE}/CnpClsMain.laf"
    params = {
        "popMenu": "ov",
        "csmSeq": csm_seq,
        "ccfNo": ccf_no,
        "cciNo": cci_no,
        "cnpClsNo": cnp_cls_no,
    }
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"    요청 실패: {e}")
        return None, None

    text = response.text

    title_start = text.find("<title>")
    title_end = text.find("</title>")
    title = html.unescape(text[title_start+7:title_end]).strip() if title_start != -1 else ""
    title = re.sub(r'\s*\(본문\)\s*\|\s*찾기쉬운 생활법령정보\s*$', '', title).strip()

    # 1) 스크립트/스타일 제거
    clean = re.sub(r'<script.*?</script>', '', text, flags=re.DOTALL)
    clean = re.sub(r'<style.*?</style>', '', clean, flags=re.DOTALL)

    # 2) 줄바꿈을 만드는 태그들을 개행문자로 치환 (태그 제거 전에 해야 함)
    clean = re.sub(r'<(br|/li|/p|/div|/tr|/h[1-6])\s*/?>', '\n', clean, flags=re.IGNORECASE)
    clean = re.sub(r'<(li|p|div|tr|h[1-6])[^>]*>', '\n', clean, flags=re.IGNORECASE)

    # 3) 나머지 태그 제거
    clean = re.sub(r'<[^>]+>', '', clean)
    clean = html.unescape(clean)

    # 4) 각 줄 내부의 중복 공백만 정리 (줄바꿈 자체는 보존), 빈 줄 제거
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in clean.split('\n')]
    lines = [line for line in lines if line]
    clean = '\n'.join(lines)

    start_marker = "본문 영역"
    end_marker = "이 정보는"
    idx_start = clean.find(start_marker)
    idx_end = clean.find(end_marker)

    if idx_start == -1 or idx_end == -1 or idx_end <= idx_start:
        return title, None

    body = clean[idx_start + len(start_marker):idx_end].strip()

    # 5) 탭 메뉴 노이즈 제거 (본문 맨 앞쪽에 줄 단위로 붙는 고정 단어들)
    noise_words = {"본문", "100문 100답", "카드뉴스", "관련법령",
                   "사례로 보는 백문백답", "이미지로 보는 카드뉴스"}
    body_lines = body.split('\n')
    while body_lines and body_lines[0].strip() in noise_words:
        body_lines.pop(0)
    # 법령 시행일 안내문도 첫 줄에 종종 섞여있어 별도 처리
    if body_lines and re.match(r'^「.+」\s*\d{4}년.*시행', body_lines[0]):
        body_lines.pop(0)
    body = '\n'.join(body_lines).strip()

    # 6) "인쇄체크" UI 텍스트 제거 (줄 중간에도 섞여 나올 수 있어 문자열 치환)
    body = body.replace("인쇄체크 ", "").replace("인쇄체크", "")

    return title, body


def is_already_saved_by_source(conn, source_url):
    """source(URL) 기준으로 이미 수집됐는지 빠르게 확인.
    ...
    """
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM tax_documents WHERE source = %s", (source_url,))
    exists = cur.fetchone() is not None
    cur.close()
    return exists


def insert_content(conn, category_name, title, body, source_url):
    """tax_documents에 적재. title 기준 중복 방지."""
    cur = conn.cursor()

    real_title = title.split(">")[-1].strip() if title else ""
    full_title = f"{category_name} - {real_title}" if real_title else category_name

    cur.execute("SELECT 1 FROM tax_documents WHERE title = %s", (full_title,))
    if cur.fetchone():
        cur.close()
        return False

    cur.execute(
        """
        INSERT INTO tax_documents (title, law_name, content, source)
        VALUES (%(title)s, %(law_name)s, %(content)s, %(source)s)
        """,
        {
            "title": full_title,
            "law_name": "생활법령정보",
            "content": body,
            "source": source_url,
        },
    )
    cur.close()
    return True


if __name__ == "__main__":
    conn = psycopg2.connect(**DB_CONFIG)
    total_inserted = 0
    total_skipped = 0
    total_no_body = 0
    total_processed = 0

    for csm_seq, category_name in ALL_CSM_SEQS.items():
        print(f"\n=== [{category_name}] (csmSeq={csm_seq}) 챕터 목록 수집 ===")
        try:
            chapters = get_chapters(csm_seq)
        except requests.exceptions.RequestException as e:
            print(f"  목록 수집 실패: {e}")
            continue
        print(f"  {len(chapters)}개 챕터 발견")
        time.sleep(REQUEST_DELAY_SECONDS)

        for ccf_no, cci_no, cnp_cls_no in chapters:
            source_url = (
                f"{BASE}/CnpClsMain.laf?popMenu=ov&csmSeq={csm_seq}"
                f"&ccfNo={ccf_no}&cciNo={cci_no}&cnpClsNo={cnp_cls_no}"
            )
            total_processed += 1
 
            if is_already_saved_by_source(conn, source_url):
                total_skipped += 1
                if total_processed % 30 == 0:
                    print(f"  {total_processed}건 처리, 누적 저장 {total_inserted}건 (건너뜀 {total_skipped}건)")
                continue
 
            title, body = fetch_content(csm_seq, ccf_no, cci_no, cnp_cls_no)
 
            if body is None:
                total_no_body += 1
                time.sleep(REQUEST_DELAY_SECONDS)
                continue
 
            if insert_content(conn, category_name, title, body, source_url):
                total_inserted += 1
                conn.commit()
            else:
                total_skipped += 1
 
            if total_processed % 30 == 0:
                print(f"  {total_processed}건 처리, 누적 저장 {total_inserted}건 (건너뜀 {total_skipped}건)")
 
            time.sleep(REQUEST_DELAY_SECONDS)
 
    conn.close()

    print()
    print("=== 전체 완료 ===")
    print(f"신규 저장: {total_inserted}건")
    print(f"건너뜀(중복): {total_skipped}건")
    print(f"본문 마커 없음: {total_no_body}건")
    print(f"총 처리: {total_processed}건")