"""구독 플랜 조회·변경. 결제는 목업이라 변경 요청을 바로 승인한다.

가격·한도·기능표는 Docs/reports/subscription_cost.md §3·§4 설계안을 따른다.
한도는 화면 표시용이며 기능을 차단하지 않는다.
"""

import calendar
from datetime import datetime

from core import repo

# 화면 플랜 표의 단일 원천. features 값: True=O, False=X, 문자열=제공 범위
PLANS = [
    {
        "key": "free",
        "name": "무료",
        "price": 0,
        "policyChatLimit": 3,
        "features": [
            {"label": "세액감면 대상 여부", "value": True},
            {"label": "예상 절감액 리포트", "value": False},
            {"label": "리포트 이력·PDF", "value": False},
            {"label": "공고지원 AI 상담", "value": "월 3회"},
            {"label": "세무 Assistant 상담", "value": True},
            {"label": "공고 검색·저장·알림·요약", "value": True},
            {"label": "D-7·D-3 맞춤 마감 알림", "value": False},
            {"label": "전체 업종 리스크 비교", "value": False},
            {"label": "지원서 초안 생성", "value": False},
        ],
    },
    {
        "key": "basic",
        "name": "베이직",
        "price": 9900,
        "policyChatLimit": 30,
        "features": [
            {"label": "세액감면 대상 여부", "value": True},
            {"label": "예상 절감액 리포트", "value": "월 10회"},
            {"label": "리포트 이력·PDF", "value": "최근 1건"},
            {"label": "공고지원 AI 상담", "value": "월 30회"},
            {"label": "세무 Assistant 상담", "value": True},
            {"label": "공고 검색·저장·알림·요약", "value": True},
            {"label": "D-7·D-3 맞춤 마감 알림", "value": False},
            {"label": "전체 업종 리스크 비교", "value": False},
            {"label": "지원서 초안 생성", "value": False},
        ],
    },
    {
        "key": "pro",
        "name": "프로",
        "price": 29000,
        "policyChatLimit": None,
        "features": [
            {"label": "세액감면 대상 여부", "value": True},
            {"label": "예상 절감액 리포트", "value": "무제한"},
            {"label": "리포트 이력·PDF", "value": "전체"},
            {"label": "공고지원 AI 상담", "value": "무제한"},
            {"label": "세무 Assistant 상담", "value": True},
            {"label": "공고 검색·저장·알림·요약", "value": True},
            {"label": "D-7·D-3 맞춤 마감 알림", "value": True},
            {"label": "전체 업종 리스크 비교", "value": True},
            {"label": "지원서 초안 생성", "value": True},
        ],
    },
]
PLAN_BY_KEY = {plan["key"]: plan for plan in PLANS}

# chat_messages.category 기준 사용량 집계 대상
POLICY_CHAT_CATEGORIES = ["policy"]
TAX_CHAT_CATEGORIES = ["tax", "expense", "saving"]


def _next_month(value: datetime) -> datetime:
    year = value.year + value.month // 12
    month = value.month % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day, microsecond=0)


def get_subscription(user_id: int) -> dict:
    row = repo.get_subscription(user_id) or {}
    plan = PLAN_BY_KEY.get(row.get("plan"), PLAN_BY_KEY["free"])
    return {
        "plans": PLANS,
        "current": {
            "plan": plan["key"],
            "startedAt": row.get("started_at"),
            "renewsAt": row.get("renews_at"),
        },
        "usage": {
            "policyChat": repo.count_chats_this_month(user_id, POLICY_CHAT_CATEGORIES),
            "policyChatLimit": plan["policyChatLimit"],
            "taxChat": repo.count_chats_this_month(user_id, TAX_CHAT_CATEGORIES),
        },
    }


def change_plan(user_id: int, plan: str) -> dict:
    # 목업 결제: 결제 대행 호출 없이 즉시 승인. 무료로 바꾸면 즉시 해지한다.
    renews_at = None if plan == "free" else _next_month(datetime.now())
    repo.upsert_subscription(user_id, plan, renews_at)
    return get_subscription(user_id)
