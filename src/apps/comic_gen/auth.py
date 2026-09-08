import os
import time
import uuid

import jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.getenv("PRISMREEL_JWT_SECRET", "").strip()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.getenv("PRISMREEL_JWT_EXPIRE_DAYS", "7"))


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


def require_login(request: Request):
    user = get_current_user_from_cookie(request)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(user=Depends(require_login)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user
