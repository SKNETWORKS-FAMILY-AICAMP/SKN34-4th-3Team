from ninja.errors import HttpError

from core import repo

# 프론트 ROADMAP_TASKS 항목 구성 버전. 순서가 바뀌면 올려 예전 체크를 무효화한다.
ROADMAP_VERSION = 2


def get_me(user_id: int) -> dict:
    user = repo.get_user(user_id)
    if not user:
        raise HttpError(404, "사용자를 찾을 수 없습니다.")
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
        raise HttpError(404, "사용자를 찾을 수 없습니다.")
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


def get_roadmap_progress(user_id: int) -> dict:
    return {"version": ROADMAP_VERSION, "done": repo.list_roadmap_done(user_id, ROADMAP_VERSION)}


def set_roadmap_task(user_id: int, task_key: str, done: bool) -> None:
    repo.set_roadmap_task(user_id, ROADMAP_VERSION, task_key, done)


def onboarding_complete(user_id: int) -> bool:
    user = repo.get_user(user_id) or {}
    profile = repo.get_profile(user_id) or {}
    return bool(user.get("age") and user.get("region") and profile.get("business_type"))
