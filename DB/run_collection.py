# =========================================================
# 전체 수집 스크립트를 순서대로 실행하는 로직
#
#   2026-09-29 수정: 
#   SQL 실행 방식을 docker exec에서 psycopg2 직접 연결로 변경함. 
#   AWS 구조에서는 이 스크립트가 App EC2(또는 GitHub
#   Actions 워크플로가 SSH로 접속한 App EC2)에서 돌고, DB는 별도의
#   Data EC2에 있어서 "docker exec startup_db"로는 접근할 수 없음.
#   대신 docker-compose.app.yml의 db-migrate 서비스가 쓰는 것과
#   같은 방식(-h COMPOSE_DB_HOST로 원격 접속)을 따름.
# =========================================================

import os
import subprocess
import sys
from pathlib import Path

import psycopg2

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"

COLLECTION_SEQUENCE = [
    "02_collect_tax_law.py",
    "11_collect_nts_interpretation.py",
    "13_collect_life_law.py",
    "03_collect_gov24.py",
    "04_collect_kstartup.py",
    "05_collect_bizinfo.py",
    "06_collect_ontong_youth.py",
    "07_generate_calendar_events.py",
]

SQL_SEQUENCE = [
    "08_link_policy_calendar.sql",
]


def get_db_config() -> dict:
    """DB 접속 정보를 환경변수에서 읽는다.

    다른 수집 스크립트(02~07번)들과 동일하게 DB_HOST/DB_PORT를 쓴다.
    (근거: Docs/AWS_MIGRATION_PLAN.md 10절 "feature/scheduler 처리
     방침" 표 — "SQL 실행부를 DB_HOST 기준으로 수정 후 병합")
    collector 서비스의 compose 정의는 아직 없어서(AWS 구조 확정 후
    작성 예정), 배포 시 .env의 DB_HOST 값을 Data EC2 주소로 설정하는
    형태가 될 것으로 보인다.
    """
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
        "dbname": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }


def run_python_script(script_name: str) -> bool:
    """수집 스크립트 하나를 실행하고 성공 여부를 반환한다."""
    script_path = SCRIPTS_DIR / script_name
    print(f"[실행] {script_name}")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        text=True,
    )
    if result.returncode != 0:
        print(f"[실패] {script_name}")
        print(result.stderr)
        return False
    print(result.stdout)
    return True


def run_sql_script(script_name: str, db_config: dict) -> bool:
    """SQL 스크립트 하나를 psycopg2로 원격 DB에 실행하고 성공 여부를 반환한다.

    docker exec startup_db 방식은 DB가 다른 호스트(Data EC2)에 있으면
    쓸 수 없어서, psycopg2로 직접 접속해 SQL 파일 내용을 실행한다.
    psycopg2는 이미 다른 수집 스크립트들이 쓰는 의존성이라 새로
    추가할 필요가 없다.
    """
    script_path = SCRIPTS_DIR.parent / script_name  # SQL 파일은 DB/ 바로 아래에 있음
    if not script_path.exists():
        script_path = SCRIPTS_DIR / script_name  # scripts/ 안에 있는 경우도 대응

    print(f"[실행] {script_name}")
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            sql_content = f.read()

        conn = psycopg2.connect(**db_config)
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(sql_content)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[실패] {script_name}: {e}")
        return False

    print(f"[완료] {script_name}")
    return True


def run_all_collection() -> dict:
    """전체 수집 파이프라인을 순서대로 실행한다.

    Returns:
        성공/실패한 스크립트 목록을 담은 결과 dict.
    """
    db_config = get_db_config()

    succeeded = []
    failed = []

    for script in COLLECTION_SEQUENCE:
        if run_python_script(script):
            succeeded.append(script)
        else:
            failed.append(script)

    for script in SQL_SEQUENCE:
        if run_sql_script(script, db_config):
            succeeded.append(script)
        else:
            failed.append(script)

    return {"succeeded": succeeded, "failed": failed}


if __name__ == "__main__":
    result = run_all_collection()
    print(f"\n완료: 성공 {len(result['succeeded'])}건, 실패 {len(result['failed'])}건")
    if result["failed"]:
        print(f"실패한 스크립트: {result['failed']}")
        sys.exit(1)