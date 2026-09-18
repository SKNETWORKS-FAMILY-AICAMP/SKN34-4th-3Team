import base64
import hashlib
import hmac
import json
import time

from core.config import TOKEN_PREFIX, TOKEN_SECRET, TOKEN_TTL_SECONDS


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_token(user_id: int, role: str = "user") -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64url(hmac.new(TOKEN_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return f"{TOKEN_PREFIX}{body}.{signature}"


def parse_token(token: str) -> tuple[str, int] | None:
    if not token.startswith(TOKEN_PREFIX):
        return None
    raw = token[len(TOKEN_PREFIX) :]
    if "." not in raw:
        return None
    body, signature = raw.rsplit(".", 1)
    expected = _b64url(hmac.new(TOKEN_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    role = payload.get("role")
    user_id = payload.get("sub")
    if role not in ("user", "admin") or not isinstance(user_id, int):
        return None
    return role, user_id
