from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core import repo
from core.security import parse_token

bearer = HTTPBearer(auto_error=False, description="로그인 응답의 accessToken을 Bearer로 넣습니다.")


def _parse(credentials: HTTPAuthorizationCredentials | None) -> tuple[str, int]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    parsed = parse_token(credentials.credentials)
    if not parsed:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    return parsed


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """사용자 토큰만 받는다.

    `users.id`와 `admin_users.id`는 별도 시퀀스라 값이 겹친다. 관리자 토큰에도
    사용자와 같은 모양의 `id`를 돌려주면 관리자가 같은 번호의 사용자로 통해
    소유자 검사가 전부 무력해진다. 그래서 관리자 토큰은 여기서 거부한다.
    """
    role, uid = _parse(credentials)
    if role == "admin":
        raise HTTPException(status_code=403, detail="관리자 토큰으로는 사용자 API를 호출할 수 없습니다.")
    user = repo.get_user(uid)
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="정지된 계정입니다.")
    return {**user, "role": "user"}


def get_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """관리자 토큰만 받는다. `id`는 `admin_users.id`다."""
    role, uid = _parse(credentials)
    if role != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    admin = repo.get_admin(uid)
    if not admin:
        raise HTTPException(status_code=401, detail="관리자를 찾을 수 없습니다.")
    return {"id": uid, "role": "admin", "email": admin["email"]}
