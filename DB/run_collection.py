# =========================================================
# 전체 수집 스크립트를 순서대로 실행하는 로직만 담당한다.
#
#   스케줄링 로직(scheduler.py)과 분리했음.
# =========================================================

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"

COLLECTION_SEQUENCE = [
    "02_collect_tax_law.py",
    "03_collect_gov24.py",
    "04_collect_kstartup.py",
    "05_collect_bizinfo.py",
    "06_collect_ontong_youth.py",
    "07_generate_calendar_events.py",
]

SQL_SEQUENCE = [
    "08_link_policy_calendar.sql",
    "09_normalize_region.sql",
]


def run_python_script(script_name: str) -> bool:
    """수집 스크립트 하나를 실행하고 성공 여부를 반환한다."""
    script_path = SCRIPTS_DIR / script_name
    print(f"[실행] {script_name}")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[실패] {script_name}")
        print(result.stderr)
        return False
    print(result.stdout)
    return True


def run_sql_script(script_name: str, db_config: dict) -> bool:
    """SQL 스크립트 하나를 DB 컨테이너 안의 psql로 실행하고 성공 여부를 반환
    """
    script_path = SCRIPTS_DIR / script_name
    print(f"[실행] {script_name}")
    with open(script_path, "r", encoding="utf-8") as sql_file:
        result = subprocess.run(
            [
                "docker", "exec", "-i", "startup_db",
                "psql",
                "-U", db_config["user"],
                "-d", db_config["dbname"],
            ],
            stdin=sql_file,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        print(f"[실패] {script_name}")
        print(result.stderr)
        return False
    print(result.stdout)
    return True


def run_all_collection() -> dict:
    """전체 수집 파이프라인을 순서대로 실행한다.

    Returns:
        성공/실패한 스크립트 목록을 담은 결과 dict.
        AWS Lambda 핸들러 등에서 결과를 그대로 반환값으로 쓸 수 있도록
        dict 형태로 설계했다.
    """
    import os
    from dotenv import load_dotenv

    load_dotenv()
    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
        "dbname": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }

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