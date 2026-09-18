from datetime import date, datetime

from fastapi import HTTPException

from core import repo
from core.llm_client import explain_tax_reduction


def diagnose(conditions: dict) -> dict:
    revenue = int(conditions.get("expectedRevenue", 0) or 0)
    has_employee = bool(conditions.get("hasEmployee", False))
    if revenue > 80_000_000 or has_employee:
        recommended = "일반과세자"
    elif revenue > 0:
        recommended = "간이과세자"
    else:
        recommended = "사업자등록 전(예비창업)"
    return {
        "recommendedType": recommended,
        "comparison": [
            {
                "type": "간이과세자",
                "when": "연 매출 8천만원 미만 예상",
                "note": "세율·신고가 단순한 편",
            },
            {
                "type": "일반과세자",
                "when": "매출 규모가 크거나 매입세액 공제가 중요할 때",
                "note": "세금계산서 발행·공제에 유리",
            },
        ],
    }


def get_tax_info(user_id: int) -> dict:
    info = repo.get_tax_info(user_id)
    if not info:
        return {"taxType": None, "details": None}
    return {"taxType": info["tax_type"], "details": info["details"]}


def update_tax_info(user_id: int, tax_info: dict) -> None:
    repo.upsert_tax_info(
        user_id,
        tax_info.get("taxType") or tax_info.get("tax_type") or "부가가치세",
        tax_info.get("details", ""),
    )


EXCLUDED_INDUSTRIES = {"유흥", "부동산임대", "사행성"}


def check_tax_reduction(user_id: int) -> dict:
    user = repo.get_user(user_id)
    profile = repo.get_profile(user_id)
    if not user or not user.get("age") or not profile or not profile.get("founded_at"):
        raise HTTPException(
            status_code=400,
            detail="개인정보와 사업자 정보(나이, 창업일)가 있어야 판정할 수 있습니다.",
        )

    reasons: list[str] = []
    eligible = True
    age = user["age"]
    if age > 39:
        eligible = False
        reasons.append(f"나이 {age}세 — 청년 요건(만 39세 이하) 미충족")
    else:
        reasons.append(f"나이 {age}세 — 청년 요건 충족")

    founded = profile["founded_at"]
    years = (date.today() - founded).days / 365
    if years > 5:
        eligible = False
        reasons.append(f"창업일 {founded} — 창업 후 5년 초과")
    else:
        reasons.append(f"창업일 {founded} — 창업 후 5년 이내")

    industry = profile.get("industry") or ""
    if any(x in industry for x in EXCLUDED_INDUSTRIES):
        eligible = False
        reasons.append(f"업종 '{industry}' — 배제 업종에 해당할 수 있음")
    else:
        reasons.append(f"업종 '{industry}' — 배제 업종으로 보이지 않음")

    explained = explain_tax_reduction(
        eligible,
        reasons,
        conditions={
            "age": user.get("age"),
            "region": user.get("region"),
            "industry": profile.get("industry"),
            "businessRegisteredAt": str(profile.get("business_registered_at") or ""),
            "foundedAt": str(profile.get("founded_at") or ""),
        },
    )
    legal_basis = (
        explained["legalBasis"]
        if explained and explained.get("legalBasis")
        else "조세특례제한법 청년창업 중소기업 세액감면 요건을 단순화한 Rule 판정입니다. 최종 판단이 아닙니다."
    )
    llm_used = bool(explained and explained.get("llmUsed"))
    repo.insert_tax_reduction(user_id, eligible, reasons, legal_basis)
    return {
        "eligible": eligible,
        "reasons": reasons,
        "legalBasis": legal_basis,
        "llmUsed": llm_used,
    }


def latest_tax_reduction(user_id: int) -> dict:
    result = repo.latest_tax_reduction(user_id)
    if not result:
        raise HTTPException(status_code=404, detail="판정 결과가 없습니다.")
    return {
        "eligible": result["eligible"],
        "reasons": result["reasons"] or [],
        "legalBasis": result.get("legalBasis") or result.get("legal_basis"),
        "llmUsed": bool(result.get("llmUsed")),
    }
