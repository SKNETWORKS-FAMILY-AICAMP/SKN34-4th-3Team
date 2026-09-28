from ninja.errors import HttpError
from ninja.security import HttpBearer

from core import repo
from core.security import parse_token


class _Bearer(HttpBearer):
    """로그인 응답의 accessToken을 Bearer로 넣습니다."""

    def __call__(self, request):
        # 헤더가 없거나 Bearer가 아니면 Ninja 기본값(None → "Unauthorized") 대신 기존 메시지로 401을 낸다.
        result = super().__call__(request)
        if result is None:
            raise HttpError(401, "로그인이 필요합니다.")
        return result

    @staticmethod
    def _parse(token: str) -> tuple[str, int]:
        parsed = parse_token(token)
        if not parsed:
            raise HttpError(401, "유효하지 않은 토큰입니다.")
        return parsed


class UserAuth(_Bearer):
    def authenticate(self, request, token: str) -> dict:
        """사용자 토큰만 받는다.

        `users.id`와 `admin_users.id`는 별도 시퀀스라 값이 겹친다. 관리자 토큰에도
        사용자와 같은 모양의 `id`를 돌려주면 관리자가 같은 번호의 사용자로 통해
        소유자 검사가 전부 무력해진다. 그래서 관리자 토큰은 여기서 거부한다.
        """
        role, uid = self._parse(token)
        if role == "admin":
            raise HttpError(403, "관리자 토큰으로는 사용자 API를 호출할 수 없습니다.")
        user = repo.get_user(uid)
        if not user:
            raise HttpError(401, "사용자를 찾을 수 없습니다.")
        if user.get("status") == "suspended":
            raise HttpError(403, "정지된 계정입니다.")
        return {**user, "role": "user"}


class AdminAuth(_Bearer):
    def authenticate(self, request, token: str) -> dict:
        """관리자 토큰만 받는다. `id`는 `admin_users.id`다."""
        role, uid = self._parse(token)
        if role != "admin":
            raise HttpError(403, "관리자 권한이 필요합니다.")
        admin = repo.get_admin(uid)
        if not admin:
            raise HttpError(401, "관리자를 찾을 수 없습니다.")
        return {"id": uid, "role": "admin", "email": admin["email"]}


user_auth = UserAuth()
admin_auth = AdminAuth()
