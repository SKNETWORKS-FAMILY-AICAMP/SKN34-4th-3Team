from datetime import date

from fastapi import HTTPException

from core import repo
from core.llm_client import summarize_announcement


def _announcement_of(policy_id: int, cache: dict[int, dict] | None = None) -> dict | None:
    if cache is not None:
        return cache.get(policy_id)
    return repo.announcement_of(policy_id)


def _to_item(
    policy: dict,
    *,
    match_score: int | None = None,
    eligible: bool | None = None,
    announcements: dict[int, dict] | None = None,
) -> dict:
    announcement = _announcement_of(policy["id"], announcements)
    return {
        "policyId": policy["id"],
        "title": policy["title"],
        "region": policy["region"],
        "industry": policy["industry"],
        "target": policy["target"],
        "benefit": policy["benefit"],
        "source": policy["source"],
        "sourceUrl": announcement.get("source_url") if announcement else None,
        "applyEndDate": announcement["apply_end_date"] if announcement else None,
        "matchScore": match_score,
        "eligible": eligible,
    }


def _to_item_for_user(
    policy: dict,
    user_id: int | None,
    announcements: dict[int, dict] | None = None,
    user: dict | None = None,
    profile: dict | None = None,
) -> dict:
    if not user_id:
        return _to_item(policy, announcements=announcements)
    user = user if user is not None else repo.get_user(user_id) or {}
    profile = profile if profile is not None else repo.get_profile(user_id) or {}
    score, ok, _ = _score_policy(policy, user, profile, announcements)
    return _to_item(policy, match_score=score, eligible=ok, announcements=announcements)


def _rank_key(item: dict):
    """자격 충족 > 판정 불가·미충족 순, 그다음 점수. None은 False로 취급한다."""
    return (item.get("eligible") is True, item.get("matchScore") or 0)


def search(
    keyword: str | None,
    region: str | None,
    industry: str | None,
    user_id: int | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[dict]:
    """SQL로 거르고, 점수화·정렬은 파이썬에서 한 뒤 페이지를 자른다.

    정렬이 전역이어야 해서 후보 전체를 점수화한 다음 자른다. 필터가 걸리면 DB가
    읽는 행이 줄고, 필터가 없어도 응답 본문은 한 페이지로 작아진다.
    """
    rows = repo.search_policies(keyword, region, industry)
    announcements = repo.announcement_map()
    user = repo.get_user(user_id) if user_id else None
    profile = repo.get_profile(user_id) if user_id else None
    items = [_to_item_for_user(p, user_id, announcements, user, profile) for p in rows]
    items.sort(key=_rank_key, reverse=True)
    return items[offset : offset + limit]


def _years_since(founded: date | None) -> float | None:
    if not founded:
        return None
    return (date.today() - founded).days / 365


def _match_rule(rule: str, user: dict, profile: dict) -> tuple[bool | None, list[str]]:
    """자격 판정. 공고에 요건이 없으면 `None`(판정 불가)을 돌려준다.

    수집된 정책 2,534건 중 2,178건은 `eligibility_rule`이 비어 있다. 예전에는 이때도
    `True`를 돌려줘 전 건이 '자격 충족'으로 표시됐고 추천이 전체 목록이 됐다.
    """
    if not (rule or "").strip():
        return None, ["공고에 자격 요건이 명시되지 않아 판정할 수 없습니다."]
    reasons = []
    ok = True
    age = user.get("age")
    region = user.get("region")
    founded_years = _years_since(profile.get("founded_at"))
    for token in (rule or "").split(","):
        token = token.strip()
        if token.startswith("age<=") and age is not None:
            limit = int(token.split("=")[1])
            hit = age <= limit
            ok = ok and hit
            reasons.append(f"나이 {age}세 / 요건 {token}: {'충족' if hit else '미충족'}")
        elif token.startswith("region=") and region:
            need = token.split("=", 1)[1]
            hit = region == need
            ok = ok and hit
            reasons.append(f"지역 {region} / 요건 {need}: {'충족' if hit else '미충족'}")
        elif token.startswith("founded_years<=") and founded_years is not None:
            limit = float(token.split("=")[1])
            hit = founded_years <= limit
            ok = ok and hit
            reasons.append(f"업력 {founded_years:.1f}년 / 요건 {token}: {'충족' if hit else '미충족'}")
        elif token.startswith("business_type!="):
            banned = token.split("!=", 1)[1]
            current = profile.get("business_type") or "미등록"
            hit = current != banned
            ok = ok and hit
            reasons.append(f"사업자 유형 {current}: {'충족' if hit else '미충족'}")
    if not reasons:
        # 요건 문구는 있으나 아는 토큰이 하나도 없다. 수집된 정책의 요건은 대부분
        # 자유 서술이라 이 경로를 탄다. 해석하지 못한 것을 '충족'으로 단정하지 않는다.
        return None, ["공고의 자격 요건을 자동으로 해석하지 못해 판정할 수 없습니다."]
    return ok, reasons


def _score_policy(
    policy: dict,
    user: dict,
    profile: dict,
    announcements: dict[int, dict] | None = None,
) -> tuple[int, bool | None, list[str]]:
    ok, reasons = _match_rule(policy.get("eligibility_rule") or "", user, profile)
    # 판정 불가(None)에는 가산하지 않는다. 충족한 것만 점수를 받는다.
    score = 20 if ok is True else 0
    region = user.get("region")
    industry = profile.get("industry")
    if policy.get("region") in (region, "전국") or not region:
        score += 30
    if policy.get("industry") in (industry, "전 업종") or not industry:
        score += 25
    announcement = _announcement_of(policy["id"], announcements)
    if announcement and announcement.get("apply_end_date"):
        remaining = (announcement["apply_end_date"] - date.today()).days
        if 0 <= remaining <= 30:
            score += 15
        elif remaining < 0:
            score -= 20
    return max(score, 0), ok, reasons


def recommendations(user_id: int, limit: int = 20) -> list[dict]:
    """상위 `limit`건만 돌려준다.

    후보는 '규칙을 실제로 충족' 또는 '점수 40 이상'이다. 판정 불가(`eligible is None`)를
    후보로 넣으면 요건 없는 정책 2,178건이 전부 추천이 되어 전체 목록과 같아진다.
    """
    user = repo.get_user(user_id) or {}
    profile = repo.get_profile(user_id) or {}
    announcements = repo.announcement_map()
    ranked = []
    for policy in repo.search_policies():
        score, ok, _ = _score_policy(policy, user, profile, announcements)
        ranked.append(_to_item(policy, match_score=score, eligible=ok, announcements=announcements))
    ranked.sort(key=_rank_key, reverse=True)
    preferred = [
        item for item in ranked
        if item.get("eligible") is True or (item.get("matchScore") or 0) >= 40
    ]
    return (preferred or ranked)[:limit]


def list_open_announcements(limit: int = 20) -> list[dict]:
    """마감이 지나지 않은 공고. 홈 화면과 지원사업 탐색이 쓴다."""
    today = date.today()
    items = []
    for row in repo.open_announcements(limit):
        end = row.get("apply_end_date")
        items.append(
            {
                "id": row["id"],
                "policyId": row["policy_id"],
                "title": row.get("title"),
                "dday": (end - today).days if end else None,
                "region": row.get("region"),
                "industry": row.get("industry"),
                "target": row.get("target"),
                "benefit": row.get("benefit"),
                "sourceUrl": row.get("source_url"),
            }
        )
    return items


def _apply_period(announcement: dict) -> str:
    """없는 쪽 날짜는 표기하지 않는다. 원천 공고에 시작일이 없는 경우가 많다."""
    start = announcement.get("apply_start_date")
    end = announcement.get("apply_end_date")
    if start and end:
        return f"{start} ~ {end}"
    if end:
        return f"~ {end}"
    if start:
        return f"{start} ~"
    return ""


def detail(policy_id: int) -> dict:
    policy = repo.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="정책을 찾을 수 없습니다.")
    announcement = _announcement_of(policy_id)
    period = ""
    method = None
    if announcement:
        period = _apply_period(announcement)
        # 컬럼은 있고 값이 NULL이면 dict.get의 기본값이 아니라 None이 온다. 그대로 내보낸다.
        method = announcement.get("apply_method")
    return {
        "policy": _to_item(policy),
        "applyPeriod": period,
        "applyMethod": method,
        "announcementId": announcement["id"] if announcement else None,
    }


def eligibility(policy_id: int, user_id: int) -> dict:
    policy = repo.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="정책을 찾을 수 없습니다.")
    user = repo.get_user(user_id) or {}
    profile = repo.get_profile(user_id) or {}
    ok, reasons = _match_rule(policy.get("eligibility_rule") or "", user, profile)
    return {"eligible": ok, "reasons": reasons}


def save_policy(user_id: int, policy_id: int) -> None:
    if not repo.get_policy(policy_id):
        raise HTTPException(status_code=404, detail="정책을 찾을 수 없습니다.")
    repo.save_policy(user_id, policy_id)


def unsave_policy(user_id: int, policy_id: int) -> None:
    """저장하지 않은 정책을 해제해도 오류로 보지 않는다. 저장과 같이 멱등이다."""
    repo.unsave_policy(user_id, policy_id)


def saved_list(user_id: int) -> list[dict]:
    # 사용자·프로필·공고를 한 번만 읽는다. 예전에는 저장 정책 1건당 커넥션 3개를 썼다.
    announcements = repo.announcement_map()
    user = repo.get_user(user_id)
    profile = repo.get_profile(user_id)
    items = []
    for pid in repo.saved_policy_ids(user_id):
        policy = repo.get_policy(pid)
        if policy:
            items.append(_to_item_for_user(policy, user_id, announcements, user, profile))
    items.sort(key=_rank_key, reverse=True)
    return items


def summarize_text(raw_content: str, source: str | None = None) -> dict:
    """붙여넣은 공고문을 LLM 서비스로 구조화한다.

    저장된 공고가 아니라 임의 텍스트라 캐시하지 않는다. 화면의 공고문 분석기가 쓴다.
    """
    body = (raw_content or "").strip()
    if not body:
        raise HTTPException(status_code=422, detail="공고문 원문이 비어 있습니다.")
    llm = summarize_announcement(body, source)
    if not llm or not llm.get("benefit"):
        raise HTTPException(status_code=503, detail="AI 요약 서비스를 사용할 수 없습니다.")
    return {
        "target": llm.get("target") or "",
        "benefit": llm.get("benefit") or "",
        "period": llm.get("period") or "",
        "documents": llm.get("documents") or "",
        "notes": llm.get("notes") or "",
        "source": llm.get("source") or source or "",
        "llmUsed": bool(llm.get("llmUsed")),
    }


def announcement_summary(announcement_id: int) -> dict:
    announcement = repo.get_announcement(announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다.")
    cached = repo.get_summary(announcement_id)
    if cached:
        return {
            "target": cached["target"],
            "benefit": cached["benefit"],
            "period": cached["period"],
            "documents": cached["documents"],
            "notes": cached["notes"],
            "source": cached["source"],
            "llmUsed": bool(cached.get("llm_used")),
        }
    raw_content = str(announcement.get("raw_content") or "").strip()
    if not raw_content:
        raise HTTPException(
            status_code=422,
            detail="공고문 원문이 없어 AI 요약을 생성할 수 없습니다.",
        )
    llm = summarize_announcement(raw_content, announcement.get("source_url"))
    if llm and llm.get("benefit"):
        summary = {
            "target": llm.get("target") or "",
            "benefit": llm.get("benefit") or "",
            "period": llm.get("period") or "",
            "documents": llm.get("documents") or "",
            "notes": llm.get("notes") or "",
            "source": llm.get("source") or announcement.get("source_url") or "",
            "llm_used": bool(llm.get("llmUsed")),
        }
        repo.upsert_summary(announcement_id, summary)
        cached = {**summary, "llm_used": summary["llm_used"]}
    if not cached:
        raise HTTPException(status_code=404, detail="공고 요약을 찾을 수 없습니다.")
    return {
        "target": cached["target"],
        "benefit": cached["benefit"],
        "period": cached["period"],
        "documents": cached["documents"],
        "notes": cached["notes"],
        "source": cached["source"],
        "llmUsed": bool(cached.get("llm_used")),
    }
