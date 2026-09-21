# =========================================================
# 언제 수집을 실행할지 결정하는 스케줄링 로직만 담당한다.
#
#   이 파일은 Docker 컨테이너에서 계속 실행되며, COLLECTION_INTERVAL_DAYS 주기마다 run_all_collection()을 호출한다.
# =========================================================

import os
import time
import schedule
from dotenv import load_dotenv

from run_collection import run_all_collection

load_dotenv()

INTERVAL_DAYS = int(os.getenv("COLLECTION_INTERVAL_DAYS", "7"))

CHECK_INTERVAL_SECONDS = int(os.getenv("SCHEDULER_CHECK_INTERVAL_SECONDS", "3600"))


def scheduled_job():
    print(f"[스케줄러] 정기 수집 시작 (주기: {INTERVAL_DAYS}일)")
    result = run_all_collection()
    print(
        f"[스케줄러] 수집 완료: 성공 {len(result['succeeded'])}건, "
        f"실패 {len(result['failed'])}건"
    )
    if result["failed"]:
        print(f"[스케줄러] 실패 목록: {result['failed']}")


def main():
    print(f"[스케줄러] 시작됨. {INTERVAL_DAYS}일마다 수집을 실행합니다.")
    schedule.every(INTERVAL_DAYS).days.do(scheduled_job)
    # schedule.every(10).seconds.do(scheduled_job)  # 테스트용: 10초마다 실행

    while True:
        schedule.run_pending()
        time.sleep(CHECK_INTERVAL_SECONDS)
        # time.sleep(5) # 테스트용


if __name__ == "__main__":
    main()