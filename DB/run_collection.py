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

import argparse
import os
import subprocess
import sys
from pathlib import Path

import psycopg2

from scripts.collect_common import EXIT_PERMANENT, EXIT_TRANSIENT

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"

# --retry 로 재실행할 대상이 없을 때의 종료 코드(.github/workflows/collect-retry.yml 이 구분한다).
EXIT_NOTHING_TO_RETRY = 3

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


def resolve_open_failures(script_name: str, db_config: dict) -> None:
    """스크립트를 다시 실행하기 전에 이전 미해결 실패를 닫는다(이번 실행이 전체를 다시 시도한다)."""
    with psycopg2.connect(**db_config) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE collection_failures SET resolved_at = now() WHERE script = %s AND resolved_at IS NULL",
            (script_name,),
        )
    conn.close()


def record_crash(script_name: str, returncode: int, attempt: int, db_config: dict) -> None:
    """실패를 기록하지 못하고 비정상 종료한 스크립트를 permanent 로 남긴다."""
    try:
        with psycopg2.connect(**db_config) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO collection_failures (script, unit, kind, reason, attempt)
                VALUES (%s, 'script', 'permanent', %s, %s)
                """,
                (script_name, f"비정상 종료(rc={returncode})", attempt),
            )
        conn.close()
    except psycopg2.Error as e:
        print(f"[기록 실패] {script_name}: {e}")


def find_due_retries(db_config: dict) -> dict:
    """재시도 시각이 지난 일시 장애가 있는 스크립트와 다음 재시도 회차를 반환한다."""
    with psycopg2.connect(**db_config) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT script, MAX(attempt) + 1
            FROM collection_failures
            WHERE kind = 'transient' AND resolved_at IS NULL AND next_retry_at <= now()
            GROUP BY script
            """
        )
        rows = cur.fetchall()
    conn.close()
    return dict(rows)


def run_python_script(script_name: str, db_config: dict, attempt: int = 0) -> int:
    """수집 스크립트 하나를 실행하고 종료 코드를 반환한다.

    0: 성공 / EXIT_TRANSIENT: 일시 장애만(자동 재실행 대상) / 그 외: 영구 장애 또는 비정상 종료
    """
    script_path = SCRIPTS_DIR / script_name
    print(f"[실행] {script_name}" + (f" (재시도 {attempt}회차)" if attempt else ""))
    resolve_open_failures(script_name, db_config)
    result = subprocess.run(
        [sys.executable, str(script_path)],
        env={**os.environ, "COLLECT_ATTEMPT": str(attempt)},
    )
    rc = result.returncode
    if rc == EXIT_TRANSIENT:
        print(f"::warning::{script_name} 일시 장애 발생, 자동 재실행 예정")
    elif rc == EXIT_PERMANENT:
        print(f"::error::{script_name} 영구 장애 발생, collection_failures 확인 필요")
    elif rc != 0:
        print(f"::error::{script_name} 비정상 종료(rc={rc})")
        record_crash(script_name, rc, attempt, db_config)
    return rc


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


def run_all_collection(retries: dict | None = None) -> dict:
    """수집 파이프라인을 순서대로 실행한다.

    Args:
        retries: {스크립트명: 재시도 회차}. 주어지면 해당 스크립트만 재실행한다.

    Returns:
        성공 / 일시 장애(자동 재실행 대상) / 실패(담당자 조치 대상) 스크립트 목록.
    """
    db_config = get_db_config()

    succeeded = []
    transient = []
    failed = []

    for script in COLLECTION_SEQUENCE:
        if retries is not None and script not in retries:
            continue
        rc = run_python_script(script, db_config, (retries or {}).get(script, 0))
        if rc == 0:
            succeeded.append(script)
        elif rc == EXIT_TRANSIENT:
            transient.append(script)
        else:
            failed.append(script)

    for script in SQL_SEQUENCE:
        if run_sql_script(script, db_config):
            succeeded.append(script)
        else:
            failed.append(script)

    return {"succeeded": succeeded, "transient": transient, "failed": failed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--retry",
        action="store_true",
        help="재시도 시각이 지난 일시 장애가 있는 스크립트만 다시 실행한다.",
    )
    args = parser.parse_args()

    retries = None
    if args.retry:
        retries = find_due_retries(get_db_config())
        if not retries:
            print("재시도 대상 없음")
            sys.exit(EXIT_NOTHING_TO_RETRY)
        print(f"재시도 대상: {retries}")

    result = run_all_collection(retries)
    print(
        f"\n완료: 성공 {len(result['succeeded'])}건, "
        f"일시 장애 {len(result['transient'])}건, 실패 {len(result['failed'])}건"
    )
    if result["transient"]:
        print(f"자동 재실행 예정: {result['transient']}")
    # 일시 장애는 collect-retry.yml 이 자동 회수하므로, 담당자 조치가 필요한 실패만 비정상 종료한다.
    if result["failed"]:
        print(f"실패한 스크립트: {result['failed']}")
        sys.exit(1)