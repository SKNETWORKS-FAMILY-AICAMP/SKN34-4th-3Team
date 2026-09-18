# =========================================================
# 국가법령정보센터 API로 법령 "전체 조문"을 수집 + DB 적재
# 
# =========================================================

import os
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

LAWS_TO_COLLECT = [
    {"name": "조세특례제한법", "mst": "280409"},
    {"name": "조세특례제한법 시행령", "mst": "287181"},
    {"name": "조세특례제한법 시행규칙", "mst": "284611"},
    {"name": "소득세법", "mst": "280405"},
    {"name": "소득세법 시행령", "mst": "286211"},
    {"name": "소득세법 시행규칙", "mst": "286379"},
    {"name": "부가가치세법", "mst": "276117"},
    {"name": "부가가치세법 시행령", "mst": "283641"},
    {"name": "부가가치세법 시행규칙", "mst": "284995"},
    {"name": "국세기본법", "mst": "288571"},
    {"name": "국세기본법 시행령", "mst": "283623"},
    {"name": "국세기본법 시행규칙", "mst": "284607"},
    {"name": "법인세법", "mst": "280349"},
    {"name": "법인세법 시행령", "mst": "283635"},
    {"name": "법인세법 시행규칙", "mst": "287787"},
    {"name": "조세범 처벌법", "mst": "224875"},
    {"name": "관세법", "mst": "288689"},
    {"name": "관세법 시행령", "mst": "283621"},
    {"name": "관세법 시행규칙", "mst": "288525"},
]


def fetch_law_body(mst):
    url = "http://www.law.go.kr/DRF/lawService.do"
    params = {"OC": OC, "target": "law", "MST": mst, "type": "JSON"}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def extract_all_articles(law_json, law_name):
    try:
        articles = law_json["법령"]["조문"]["조문단위"]
    except KeyError:
        print(f"⚠️ [{law_name}] 예상한 구조와 다릅니다. 최상위 키: {law_json.keys()}")
        return []

    rows = []
    for article in articles:
        title = article.get("조문제목", "") or ""
        base_content = (article.get("조문내용", "") or "").strip()

        hang_list = article.get("항")
        hang_texts = []
        if isinstance(hang_list, list):
            for h in hang_list:
                if isinstance(h, dict) and h.get("항내용"):
                    hang_texts.append(h["항내용"])
        elif isinstance(hang_list, dict) and hang_list.get("항내용"):
            hang_texts.append(hang_list["항내용"])

        content = base_content
        if hang_texts:
            content = (base_content + "\n" + "\n".join(hang_texts)).strip()

        if not content.strip():
            continue  # 내용이 아예 비어있는 조문(삭제된 조문 등)은 건너뜀

        rows.append({
            "title": f"{law_name} 제{article.get('조문번호','?')}조 {title}".strip(),
            "law_name": law_name,
            "content": content,
            "source": "https://www.law.go.kr",
        })

    print(f"  └ [{law_name}] 전체 {len(articles)}개 조문 중 {len(rows)}개 저장 대상 (빈 조문 제외)")
    return rows


def insert_tax_documents(rows):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    inserted = 0
    for row in rows:
        cur.execute("SELECT 1 FROM tax_documents WHERE title = %s", (row["title"],))
        if cur.fetchone():
            continue

        cur.execute(
            """
            INSERT INTO tax_documents (title, law_name, content, source)
            VALUES (%(title)s, %(law_name)s, %(content)s, %(source)s)
            """,
            row,
        )
        inserted += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"  └ 신규 {inserted}건 저장 (중복 {len(rows) - inserted}건은 건너뜀)")


if __name__ == "__main__":
    for law in LAWS_TO_COLLECT:
        print(f"[{law['name']}] 수집 시작...")
        law_json = fetch_law_body(law["mst"])
        rows = extract_all_articles(law_json, law["name"])
        insert_tax_documents(rows)
        time.sleep(1)

    print("전체 법령 수집 완료!")