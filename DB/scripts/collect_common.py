# =========================================================
# 수집 스크립트 공통: 외부 요청 실패 분류 + 실패 단위 기록
#
#   일시 장애(timeout·연결 오류·5xx·429·트래픽 초과)는 collection_failures 에
#   transient 로 남기고, run_collection.py --retry(.github/workflows/collect-retry.yml)
#   가 3시간 간격으로 해당 스크립트를 다시 실행한다. 재시도 3회를 넘기거나
#   영구 장애(키 만료·권한·응답 구조 변경)면 permanent 로 남겨 담당자가 조치한다.
# =========================================================

import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

# 스크립트 종료 코드. run_collection.py 가 이 값으로 결과를 구분한다.
EXIT_TRANSIENT = 75  # 일시 장애만 있음 → 자동 재실행 대상
EXIT_PERMANENT = 76  # 영구 장애 포함 → 담당자 조치 대상

MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = timedelta(hours=2)  # 재시도 cron(3시간 간격)의 다음 회차에 잡히도록 조금 짧게

KST = timezone(timedelta(hours=9))

RETRY_STATUSES = {403, 429, 500, 502, 503, 504}

# 공공데이터포털(data.go.kr)은 오류도 HTTP 200 + XML 본문으로 돌려준다.
_DATA_GO_KR_CODE = re.compile(r"<returnReasonCode>\s*(\d+)\s*</returnReasonCode>")
_DATA_GO_KR_QUOTA_CODE = "22"  # LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR

_failures = {"transient": 0, "permanent": 0}


class TransientError(Exception):
    """시간이 지나면 풀릴 수 있는 장애. retry_at 이 있으면 그 시각 이후에 재시도한다."""

    def __init__(self, reason, retry_at=None):
        super().__init__(reason)
        self.retry_at = retry_at


class PermanentError(Exception):
    """재시도로는 풀리지 않는 장애(키 만료·권한·응답 구조 변경 등)."""


def _next_kst_midnight():
    tomorrow = datetime.now(KST).date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 10, tzinfo=KST)


def _check_data_go_kr_error(response):
    match = _DATA_GO_KR_CODE.search(response.text[:2000])
    if not match:
        return
    code = match.group(1)
    if code == _DATA_GO_KR_QUOTA_CODE:
        # 일일 트래픽은 자정에 초기화되므로 당일 재시도는 의미가 없다.
        raise TransientError("data.go.kr 일일 트래픽 초과(code=22)", retry_at=_next_kst_midnight())
    raise PermanentError(f"data.go.kr 오류(code={code})")


def request(method, url, max_retries=3, **kwargs):
    """외부 요청을 보내고 실패를 TransientError / PermanentError 로 분류한다.

    일시 장애는 프로세스 안에서 짧게(5·10초) 재시도한 뒤에도 실패하면 올린다.
    """
    kwargs.setdefault("timeout", 30)
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.request(method, url, **kwargs)
        except requests.exceptions.RequestException as e:
            if attempt == max_retries:
                raise TransientError(f"요청 오류({type(e).__name__})") from None
            wait = 5 * attempt
            print(f"  요청 오류({type(e).__name__}), {wait}초 후 재시도 ({attempt}/{max_retries})")
            time.sleep(wait)
            continue

        if response.status_code == 200:
            _check_data_go_kr_error(response)
            return response

        if response.status_code in RETRY_STATUSES and attempt < max_retries:
            wait = 5 * attempt
            print(f"  status={response.status_code}, {wait}초 후 재시도 ({attempt}/{max_retries})")
            time.sleep(wait)
            continue

        reason = f"status={response.status_code}"
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientError(reason)
        raise PermanentError(reason)


def json_of(response):
    """응답을 JSON 으로 읽는다. 형식이 바뀌어 읽을 수 없으면 영구 장애로 본다."""
    try:
        return response.json()
    except ValueError:
        raise PermanentError(f"JSON 응답 아님: {response.text[:200]!r}") from None


def record_failure(conn, unit, exc):
    """실패 단위를 collection_failures 에 남긴다.

    conn 은 스크립트의 적재 커넥션으로, 진행 중이던 트랜잭션을 되돌린다.
    기록은 별도 커넥션으로 바로 commit 해 스크립트 쪽 롤백과 무관하게 남긴다.
    """
    if conn is not None:
        conn.rollback()

    script = os.path.basename(sys.argv[0])
    attempt = int(os.getenv("COLLECT_ATTEMPT", "0"))
    reason = str(exc) or type(exc).__name__
    next_retry_at = None

    if isinstance(exc, TransientError) and attempt < MAX_RETRY_ATTEMPTS:
        kind = "transient"
        next_retry_at = exc.retry_at or datetime.now(timezone.utc) + RETRY_DELAY
    else:
        kind = "permanent"
        if isinstance(exc, TransientError):
            reason = f"재시도 {MAX_RETRY_ATTEMPTS}회 초과: {reason}"
        elif not isinstance(exc, PermanentError):
            reason = f"{type(exc).__name__}: {reason}"

    _failures[kind] += 1
    print(f"  [실패:{kind}] {unit} - {reason}")

    record_conn = psycopg2.connect(**DB_CONFIG)
    try:
        with record_conn, record_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO collection_failures (script, unit, kind, reason, attempt, next_retry_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (script, unit[:255], kind, reason, attempt, next_retry_at),
            )
    finally:
        record_conn.close()


def exit_code():
    """스크립트 마지막에 sys.exit(exit_code()) 로 결과를 run_collection.py 에 알린다."""
    if _failures["permanent"]:
        return EXIT_PERMANENT
    if _failures["transient"]:
        return EXIT_TRANSIENT
    return 0
