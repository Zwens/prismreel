import os
import time
import uuid

import jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.getenv("PRISMREEL_JWT_SECRET", "").strip()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.getenv("PRISMREEL_JWT_EXPIRE_DAYS", "7"))

# 留空 = 完全停用登入閘門，比照既有 PRISMREEL_API_KEY 的慣例（desktop 單機
# 模式維持現狀、也是 spec §8 的緊急回滾手段）。但一旦「有設定」，就不能是
# 隨手打的弱密鑰——非空但過短會被 HS256 暴力破解，這裡直接拒絕啟動而不是
# 静默接受。
if JWT_SECRET and len(JWT_SECRET) < 32:
    raise RuntimeError(
        "PRISMREEL_JWT_SECRET is set but shorter than 32 characters. "
        "Use a strong random value (e.g. `openssl rand -hex 32`), or unset it entirely to disable the login gate."
    )


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str) -> str:
    now = time.time()
    payload = {
        "user_id": user_id,
        "role": role,
        "iat": now,
        "exp": now + JWT_EXPIRE_DAYS * 86400,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def new_uuid() -> str:
    return uuid.uuid4().hex


from fastapi import Request, HTTPException, Depends
from . import user_repo


def get_current_user_from_cookie(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except jwt.InvalidTokenError:
        return None
    return user_repo.get_user_by_id(payload.get("user_id"))


# Used only when JWT_SECRET is unset (login gate disabled, see the comment
# at the top of this module). Carries role="admin" so owner_id filtering in
# route handlers (e.g. `if user.role != "admin": filter by owner`) grants
# full access, matching "gate disabled" meaning "behave like the single-user
# desktop mode that predates auth" rather than a locked-out empty result.
#
# Built lazily (not at module import time): `user_repo` imports from this
# module before its own `User` class is defined, so referencing
# `user_repo.User` here at module scope deadlocks any entrypoint that
# imports `user_repo` first (e.g. scripts/migrate_auth_v1.py).
_anonymous_admin: "user_repo.User | None" = None


def _get_anonymous_admin():
    global _anonymous_admin
    if _anonymous_admin is None:
        _anonymous_admin = user_repo.User(
            id="anonymous",
            email="",
            password_hash="",
            role="admin",
            display_name="Anonymous",
            created_at=0.0,
            is_active=True,
        )
    return _anonymous_admin


def require_login(request: Request):
    if not JWT_SECRET:
        return _get_anonymous_admin()
    user = get_current_user_from_cookie(request)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(user=Depends(require_login)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user
