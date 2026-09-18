from fastapi import HTTPException

from core import repo


def get_me(user_id: int) -> dict:
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "age": user.get("age"),
        "region": user.get("region"),
        "phone": user.get("phone") or "",
    }


def update_me(user_id: int, payload: dict) -> None:
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    repo.update_user(
        user_id,
        {key: payload[key] for key in ("name", "age", "region", "phone") if payload.get(key) is not None},
    )


def get_business_profile(user_id: int) -> dict:
    profile = repo.get_profile(user_id)
    if not profile:
        return {
            "businessType": None,
            "industry": None,
            "businessRegisteredAt": None,
            "foundedAt": None,
        }
    return {
        "businessType": profile.get("business_type"),
        "industry": profile.get("industry"),
        "businessRegisteredAt": profile.get("business_registered_at"),
        "foundedAt": profile.get("founded_at"),
    }


def update_business_profile(user_id: int, payload: dict) -> None:
    repo.upsert_profile(user_id, payload)


def onboarding_complete(user_id: int) -> bool:
    user = repo.get_user(user_id) or {}
    profile = repo.get_profile(user_id) or {}
    return bool(user.get("age") and user.get("region") and profile.get("business_type"))
