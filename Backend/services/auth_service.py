from fastapi import HTTPException

from core import repo
from core.security import create_token, hash_password, verify_password


def signup(email: str, password: str, name: str) -> int:
    if repo.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")
    return repo.create_user(email, hash_password(password), name)


def login(email: str, password: str) -> dict:
    user = repo.get_user_by_email(email)
    if user is None or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="정지된 계정입니다. 관리자에게 문의하세요.")
    return {
        "accessToken": create_token(user["id"], "user"),
        "userId": user["id"],
        "name": user["name"],
        "role": "user",
    }


def admin_login(email: str, password: str) -> dict:
    admin = repo.get_admin_by_email(email)
    if admin is None or not verify_password(password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="관리자 인증에 실패했습니다.")
    return {
        "accessToken": create_token(admin["id"], "admin"),
        "userId": admin["id"],
        "name": "관리자",
        "role": "admin",
    }
