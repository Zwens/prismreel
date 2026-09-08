# 多租戶帳號登入系統 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `prismreel.soulo-ai.com`（Docker Compose 部署）從無登入的裸奔狀態，改造成邀請制多租戶 SaaS——每個使用者只看得到自己的 Script/Series，密碼與 session 用 JWT + HttpOnly Cookie 保護。

**Architecture:** 新增 SQLite (`output/auth.db`) 存 users/invites，`src/apps/comic_gen/auth.py` 提供 bcrypt hash + JWT 簽發/驗證 + 一組 FastAPI dependency。既有 `Script`/`Series` 加 `owner_id` 欄位，用一個共用 dependency（`get_owned_script`/`get_owned_series`）取代現有 60+ 個端點手寫的 `pipeline.get_script(id)` + 404 樣板，一次到位套用 owner 過濾。`/files/users/...` 新路徑用自訂 middleware 做 owner 比對，`/files/` 舊全域路徑維持不變（相容既有資料，見 Task 5 說明）。前端新增登入頁、admin 後台、邀請落地頁，全域 axios 加 `withCredentials` 與 401 攔截。

**Tech Stack:** FastAPI + Pydantic（既有）、`passlib[bcrypt]`（新增）、`PyJWT`（已在 requirements）、SQLite（stdlib `sqlite3`）、Next.js 14 App Router + axios + Zustand（既有）。

**Spec:** `docs/superpowers/specs/2026-09-08-multi-tenant-auth-design.md`

## Global Constraints

- Desktop 單機模式（`python main.py`，`127.0.0.1`）行為不變——`PRISMREEL_JWT_SECRET` 未設定時 `enforce_login` middleware 完全停用（比照現有 `PRISMREEL_API_KEY` 留空=不驗證的慣例）。
- 密碼一律 bcrypt hash，JWT 密鑰讀 `PRISMREEL_JWT_SECRET`，HS256，預設效期 7 天（`PRISMREEL_JWT_EXPIRE_DAYS`）。
- 建帳一律邀請制，不開放自助註冊端點。
- 全域資產庫 `GlobalAssetLibrary`（`models.py:699`）**不加** `owner_id`，維持全域共享。
- 非 owner 存取他人 `project_id`/`series_id` 一律回 404（不回 403），避免資源存在性洩漏。
- 登入失敗一律回「帳號或密碼錯誤」，不區分帳號不存在或密碼錯。
- 新增依賴只放進 `requirements-docker.txt`（Docker build 用）與根目錄 `requirements.txt` 兩份，不能只改一份。
- `/files/` 舊路徑（`output/assets`、`output/video` 等既有全域掛載）維持現狀不做強制驗證——只有新建專案採用的 `output/users/{owner_id}/...` 新路徑受 middleware 保護（理由見 Task 5）。

---

## Task 1: SQLite Schema + Auth 核心模組

**Files:**
- Create: `src/apps/comic_gen/auth_db.py`
- Create: `src/apps/comic_gen/auth.py`
- Create: `src/apps/comic_gen/test_auth.py`
- Modify: `requirements.txt`（新增一行）
- Modify: `requirements-docker.txt`（新增一行）

**Interfaces:**
- Produces:
  - `auth_db.get_connection() -> sqlite3.Connection`（`output/auth.db`，`row_factory = sqlite3.Row`）
  - `auth_db.init_schema(conn) -> None`（建 `users`/`invites` 表，冪等：`CREATE TABLE IF NOT EXISTS`）
  - `auth.hash_password(plain: str) -> str`
  - `auth.verify_password(plain: str, hashed: str) -> bool`
  - `auth.create_access_token(user_id: str, role: str) -> str`
  - `auth.decode_access_token(token: str) -> dict`（拋 `jwt.InvalidTokenError` 子類例外，caller 負責轉 401）
  - `auth.JWT_SECRET: str`（模組載入時讀 `os.getenv("PRISMREEL_JWT_SECRET", "")`）

- [ ] **Step 1: 新增依賴**

`requirements.txt` 在 `PyJWT>=2.8.0` 那行後面加一行：

```
passlib[bcrypt]>=1.7.4
```

`requirements-docker.txt` 同樣位置加同一行。

- [ ] **Step 2: 安裝依賴到本機開發環境驗證可用**

Run: `pip install "passlib[bcrypt]>=1.7.4"`
Expected: 安裝成功，無編譯錯誤

- [ ] **Step 3: 寫失敗測試（密碼 hash/verify）**

`src/apps/comic_gen/test_auth.py`:

```python
import os
import pytest


def test_hash_and_verify_password_roundtrip():
    from src.apps.comic_gen.auth import hash_password, verify_password

    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_create_and_decode_access_token(monkeypatch):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-for-unit-tests")
    import importlib
    from src.apps.comic_gen import auth
    importlib.reload(auth)

    token = auth.create_access_token(user_id="user-123", role="member")
    payload = auth.decode_access_token(token)
    assert payload["user_id"] == "user-123"
    assert payload["role"] == "member"


def test_decode_access_token_rejects_garbage(monkeypatch):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-for-unit-tests")
    import importlib
    from src.apps.comic_gen import auth
    importlib.reload(auth)
    import jwt as pyjwt

    with pytest.raises(pyjwt.InvalidTokenError):
        auth.decode_access_token("not-a-real-token")
```

- [ ] **Step 4: 執行測試確認失敗（模組尚不存在）**

Run: `pytest src/apps/comic_gen/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.apps.comic_gen.auth'`

- [ ] **Step 5: 實作 `auth_db.py`**

```python
import os
import sqlite3
import threading

_DB_PATH = os.path.join("output", "auth.db")
_lock = threading.RLock()


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    with _lock:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                display_name TEXT,
                created_at REAL NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invites (
                code TEXT PRIMARY KEY,
                created_by TEXT NOT NULL REFERENCES users(id),
                email_hint TEXT,
                role TEXT NOT NULL DEFAULT 'member',
                created_at REAL NOT NULL,
                used_at REAL,
                used_by TEXT REFERENCES users(id)
            )
            """
        )
        conn.commit()
```

- [ ] **Step 6: 實作 `auth.py`**

```python
import os
import time
import uuid
from typing import Optional

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
```

- [ ] **Step 7: 執行測試確認通過**

Run: `pytest src/apps/comic_gen/test_auth.py -v`
Expected: PASS（3 tests）

- [ ] **Step 8: Commit**

```bash
git add src/apps/comic_gen/auth.py src/apps/comic_gen/auth_db.py src/apps/comic_gen/test_auth.py requirements.txt requirements-docker.txt
git commit -m "feat(auth): add password hashing and JWT token core module"
```

---

## Task 2: User Repository + FastAPI Dependencies

**Files:**
- Create: `src/apps/comic_gen/user_repo.py`
- Create: `src/apps/comic_gen/test_user_repo.py`
- Modify: `src/apps/comic_gen/auth.py`（加 dependency 函式）

**Interfaces:**
- Consumes: `auth_db.get_connection`, `auth_db.init_schema`, `auth.hash_password`, `auth.verify_password`, `auth.decode_access_token`, `auth.new_uuid`（Task 1）
- Produces:
  - `user_repo.User`（dataclass：`id, email, password_hash, role, display_name, created_at, is_active`）
  - `user_repo.create_user(email, password, role="member", display_name=None) -> User`
  - `user_repo.get_user_by_email(email) -> Optional[User]`
  - `user_repo.get_user_by_id(user_id) -> Optional[User]`
  - `user_repo.list_users() -> list[User]`
  - `user_repo.set_password(user_id, new_password) -> None`
  - `user_repo.set_active(user_id, is_active: bool) -> None`
  - `user_repo.create_invite(created_by, role="member", email_hint=None) -> str`（回傳 invite code）
  - `user_repo.redeem_invite(code, email, password) -> User`（拋 `ValueError` 若 code 無效/已用）
  - `auth.get_current_user_from_cookie(request: Request) -> Optional[User]`（cookie 缺失或驗證失敗回 `None`，不拋例外）
  - `auth.require_login(request: Request) -> User`（FastAPI dependency，`None` 時拋 `HTTPException(401)`）
  - `auth.require_admin(user: User = Depends(require_login)) -> User`（`role != "admin"` 拋 `HTTPException(403)`）

- [ ] **Step 1: 寫失敗測試**

`src/apps/comic_gen/test_user_repo.py`:

```python
import os
import tempfile
import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret")
    import importlib
    from src.apps.comic_gen import auth_db, user_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(user_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def test_create_and_get_user_by_email():
    from src.apps.comic_gen import user_repo

    created = user_repo.create_user("alice@example.com", "hunter2", role="admin")
    fetched = user_repo.get_user_by_email("alice@example.com")
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.role == "admin"
    assert fetched.password_hash != "hunter2"


def test_create_user_duplicate_email_raises():
    from src.apps.comic_gen import user_repo

    user_repo.create_user("bob@example.com", "pw1")
    with pytest.raises(Exception):
        user_repo.create_user("bob@example.com", "pw2")


def test_invite_lifecycle():
    from src.apps.comic_gen import user_repo

    admin = user_repo.create_user("admin@example.com", "adminpw", role="admin")
    code = user_repo.create_invite(created_by=admin.id, role="member")

    new_user = user_repo.redeem_invite(code, "newmember@example.com", "memberpw")
    assert new_user.role == "member"

    with pytest.raises(ValueError):
        user_repo.redeem_invite(code, "another@example.com", "pw")


def test_redeem_invite_invalid_code_raises():
    from src.apps.comic_gen import user_repo

    with pytest.raises(ValueError):
        user_repo.redeem_invite("does-not-exist", "x@example.com", "pw")
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest src/apps/comic_gen/test_user_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.apps.comic_gen.user_repo'`

- [ ] **Step 3: 實作 `user_repo.py`**

```python
import time
from dataclasses import dataclass
from typing import Optional

from .auth_db import get_connection
from .auth import hash_password, verify_password, new_uuid


@dataclass
class User:
    id: str
    email: str
    password_hash: str
    role: str
    display_name: Optional[str]
    created_at: float
    is_active: bool


def _row_to_user(row) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"],
        role=row["role"],
        display_name=row["display_name"],
        created_at=row["created_at"],
        is_active=bool(row["is_active"]),
    )


def create_user(email: str, password: str, role: str = "member", display_name: Optional[str] = None) -> User:
    conn = get_connection()
    try:
        user_id = new_uuid()
        created_at = time.time()
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, display_name, created_at, is_active) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (user_id, email, hash_password(password), role, display_name, created_at),
        )
        conn.commit()
        return User(user_id, email, hash_password(password), role, display_name, created_at, True)
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[User]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: str) -> Optional[User]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def list_users() -> list[User]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
        return [_row_to_user(r) for r in rows]
    finally:
        conn.close()


def set_password(user_id: str, new_password: str) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), user_id))
        conn.commit()
    finally:
        conn.close()


def set_active(user_id: str, is_active: bool) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
        conn.commit()
    finally:
        conn.close()


def create_invite(created_by: str, role: str = "member", email_hint: Optional[str] = None) -> str:
    conn = get_connection()
    try:
        code = new_uuid()
        conn.execute(
            "INSERT INTO invites (code, created_by, email_hint, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (code, created_by, email_hint, role, time.time()),
        )
        conn.commit()
        return code
    finally:
        conn.close()


def redeem_invite(code: str, email: str, password: str) -> User:
    conn = get_connection()
    try:
        invite = conn.execute("SELECT * FROM invites WHERE code = ?", (code,)).fetchone()
        if not invite:
            raise ValueError("Invalid invite code")
        if invite["used_at"] is not None:
            raise ValueError("Invite code already used")

        user_id = new_uuid()
        created_at = time.time()
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, display_name, created_at, is_active) VALUES (?, ?, ?, ?, NULL, ?, 1)",
            (user_id, email, hash_password(password), invite["role"], created_at),
        )
        conn.execute(
            "UPDATE invites SET used_at = ?, used_by = ? WHERE code = ?",
            (created_at, user_id, code),
        )
        conn.commit()
        return User(user_id, email, hash_password(password), invite["role"], None, created_at, True)
    finally:
        conn.close()
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest src/apps/comic_gen/test_user_repo.py -v`
Expected: PASS（4 tests）

- [ ] **Step 5: 在 `auth.py` 加入 FastAPI dependency**

在 `src/apps/comic_gen/auth.py` 末尾追加：

```python
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
```

- [ ] **Step 6: 執行全部 auth 相關測試確認無迴歸**

Run: `pytest src/apps/comic_gen/test_auth.py src/apps/comic_gen/test_user_repo.py -v`
Expected: PASS（7 tests）

- [ ] **Step 7: Commit**

```bash
git add src/apps/comic_gen/user_repo.py src/apps/comic_gen/test_user_repo.py src/apps/comic_gen/auth.py
git commit -m "feat(auth): add user repository and FastAPI auth dependencies"
```

---

## Task 3: `/auth/*` 與 `/admin/*` API 端點

**Files:**
- Modify: `src/apps/comic_gen/api.py`

**Interfaces:**
- Consumes: `auth.require_login`, `auth.require_admin`, `auth.create_access_token`, `auth.JWT_SECRET`（Task 1/2）, `user_repo.*`（Task 2）
- Produces: `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/redeem_invite`, `/admin/invites`, `/admin/users`, `/admin/users/{id}/reset_password`, `/admin/users/{id}/deactivate` 端點，供前端 Task 8-11 呼叫

- [ ] **Step 1: 在 `api.py` 加 import**

在既有 `from .pipeline import ...` 附近加：

```python
from . import auth, user_repo
```

- [ ] **Step 2: 新增 `/auth/*` 端點**

放在 `pipeline = ComicGenPipeline()`（api.py:171）之後：

```python
from pydantic import BaseModel as _BaseModel


class LoginRequest(_BaseModel):
    email: str
    password: str


class RedeemInviteRequest(_BaseModel):
    invite_code: str
    email: str
    password: str


@app.post("/auth/login")
def login(body: LoginRequest, response: JSONResponse):
    user = user_repo.get_user_by_email(body.email)
    if not user or not user.is_active or not auth.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    token = auth.create_access_token(user.id, user.role)
    resp = JSONResponse({"id": user.id, "email": user.email, "role": user.role, "display_name": user.display_name})
    resp.set_cookie(
        "access_token", token,
        httponly=True, secure=True, samesite="lax",
        max_age=auth.JWT_EXPIRE_DAYS * 86400,
    )
    return resp


@app.post("/auth/logout")
def logout(_user=Depends(auth.require_login)):
    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie("access_token")
    return resp


@app.get("/auth/me")
def auth_me(user=Depends(auth.require_login)):
    return {"id": user.id, "email": user.email, "role": user.role, "display_name": user.display_name}


@app.post("/auth/redeem_invite")
def redeem_invite(body: RedeemInviteRequest):
    try:
        user = user_repo.redeem_invite(body.invite_code, body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = auth.create_access_token(user.id, user.role)
    resp = JSONResponse({"id": user.id, "email": user.email, "role": user.role})
    resp.set_cookie(
        "access_token", token,
        httponly=True, secure=True, samesite="lax",
        max_age=auth.JWT_EXPIRE_DAYS * 86400,
    )
    return resp
```

注意：`Depends` 需要從 `fastapi` import——檢查 api.py 第 23 行的 import 陳述式，若尚未包含 `Depends`，補上。

- [ ] **Step 3: 新增 `/admin/*` 端點**

緊接在上面之後：

```python
class CreateInviteRequest(_BaseModel):
    role: str = "member"
    email_hint: Optional[str] = None


class ResetPasswordRequest(_BaseModel):
    new_password: str


@app.post("/admin/invites")
def admin_create_invite(body: CreateInviteRequest, admin=Depends(auth.require_admin)):
    code = user_repo.create_invite(created_by=admin.id, role=body.role, email_hint=body.email_hint)
    return {"invite_code": code}


@app.get("/admin/users")
def admin_list_users(_admin=Depends(auth.require_admin)):
    return [
        {"id": u.id, "email": u.email, "role": u.role, "display_name": u.display_name, "is_active": u.is_active, "created_at": u.created_at}
        for u in user_repo.list_users()
    ]


@app.post("/admin/users/{user_id}/reset_password")
def admin_reset_password(user_id: str, body: ResetPasswordRequest, _admin=Depends(auth.require_admin)):
    if not user_repo.get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    user_repo.set_password(user_id, body.new_password)
    return {"status": "password_reset"}


@app.post("/admin/users/{user_id}/deactivate")
def admin_deactivate_user(user_id: str, _admin=Depends(auth.require_admin)):
    if not user_repo.get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    user_repo.set_active(user_id, False)
    return {"status": "deactivated"}
```

- [ ] **Step 4: 確認 `Depends` 已 import**

Run: `python -c "import ast; ast.parse(open('src/apps/comic_gen/api.py', encoding='utf-8').read())"`
Expected: 無 SyntaxError。若 `Depends` 未定義，於檔案頂部 `from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Request` 這行加上 `, Depends`。

- [ ] **Step 5: 手動啟動 server 驗證新端點掛載成功**

Run（PowerShell，背景執行後立即測試再關閉）:
```
$env:PRISMREEL_JWT_SECRET="dev-test-secret"
$env:PRISMREEL_ADMIN_EMAIL="admin@test.local"
$env:PRISMREEL_ADMIN_PASSWORD="devpassword123"
python -m uvicorn src.apps.comic_gen.api:app --port 17178 &
```
然後：
```
curl -s -X POST http://127.0.0.1:17178/auth/login -H "Content-Type: application/json" -d "{\"email\":\"nonexistent@test.local\",\"password\":\"wrong\"}"
```
Expected: `{"detail":"帳號或密碼錯誤"}`，HTTP 401（此時尚未跑遷移腳本，`users` 表可能是空的，這只驗證端點存在且回應格式正確，帳號實際建立在 Task 4）

- [ ] **Step 6: Commit**

```bash
git add src/apps/comic_gen/api.py
git commit -m "feat(auth): add /auth/* and /admin/* endpoints"
```

---

## Task 4: 遷移腳本 `scripts/migrate_auth_v1.py`

**Files:**
- Create: `scripts/migrate_auth_v1.py`
- Create: `scripts/test_migrate_auth_v1.py`

**Interfaces:**
- Consumes: `auth_db.get_connection`, `auth_db.init_schema`（Task 1）, `user_repo.create_user`, `user_repo.list_users`（Task 2）
- Produces: 執行後 `output/auth.db` 有 schema + 一個 admin 帳號；`output/projects.json`、`output/series.json` 每筆記錄補上 `owner_id`；`output/.auth_migrated` marker 檔

- [ ] **Step 1: 寫失敗測試**

`scripts/test_migrate_auth_v1.py`:

```python
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_migration_creates_admin_and_marker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRISMREEL_ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("PRISMREEL_ADMIN_PASSWORD", "testpassword123")
    os.makedirs("output", exist_ok=True)
    with open("output/projects.json", "w") as f:
        json.dump({"proj-1": {"id": "proj-1", "title": "Old Project"}}, f)

    import importlib
    from src.apps.comic_gen import auth_db, user_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", os.path.join(str(tmp_path), "output", "auth.db"))
    importlib.reload(user_repo)

    import scripts.migrate_auth_v1 as migrate
    importlib.reload(migrate)
    migrate.run()

    assert os.path.exists("output/.auth_migrated")
    users = user_repo.list_users()
    assert len(users) == 1
    assert users[0].role == "admin"

    with open("output/projects.json") as f:
        data = json.load(f)
    assert data["proj-1"]["owner_id"] == users[0].id


def test_migration_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRISMREEL_ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("PRISMREEL_ADMIN_PASSWORD", "testpassword123")
    os.makedirs("output", exist_ok=True)
    with open("output/projects.json", "w") as f:
        json.dump({}, f)

    import importlib
    from src.apps.comic_gen import auth_db, user_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", os.path.join(str(tmp_path), "output", "auth.db"))
    importlib.reload(user_repo)

    import scripts.migrate_auth_v1 as migrate
    importlib.reload(migrate)
    migrate.run()
    migrate.run()

    assert len(user_repo.list_users()) == 1


def test_migration_requires_admin_env_vars(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PRISMREEL_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("PRISMREEL_ADMIN_PASSWORD", raising=False)
    os.makedirs("output", exist_ok=True)

    import importlib
    from src.apps.comic_gen import auth_db
    monkeypatch.setattr(auth_db, "_DB_PATH", os.path.join(str(tmp_path), "output", "auth.db"))

    import scripts.migrate_auth_v1 as migrate
    importlib.reload(migrate)

    import pytest
    with pytest.raises(SystemExit):
        migrate.run()
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest scripts/test_migrate_auth_v1.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.migrate_auth_v1'`

- [ ] **Step 3: 實作遷移腳本**

`scripts/migrate_auth_v1.py`:

```python
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.apps.comic_gen import auth_db, user_repo


def _ensure_admin() -> str:
    users = user_repo.list_users()
    admin_users = [u for u in users if u.role == "admin"]
    if admin_users:
        return admin_users[0].id

    email = os.getenv("PRISMREEL_ADMIN_EMAIL", "").strip()
    password = os.getenv("PRISMREEL_ADMIN_PASSWORD", "").strip()
    if not email or not password:
        print("[migrate_auth_v1] ERROR: PRISMREEL_ADMIN_EMAIL and PRISMREEL_ADMIN_PASSWORD must be set for first-run migration.")
        sys.exit(1)

    admin = user_repo.create_user(email, password, role="admin", display_name="Admin")
    print(f"[migrate_auth_v1] Created admin account: {email}")
    return admin.id


def _backfill_owner_id(json_path: str, admin_id: str) -> None:
    if not os.path.exists(json_path):
        return
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    changed = False
    for record in data.values():
        if isinstance(record, dict) and "owner_id" not in record:
            record["owner_id"] = admin_id
            changed = True
    if changed:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[migrate_auth_v1] Backfilled owner_id in {json_path}")


def run() -> None:
    marker = os.path.join("output", ".auth_migrated")
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()

    admin_id = _ensure_admin()

    if not os.path.exists(marker):
        _backfill_owner_id(os.path.join("output", "projects.json"), admin_id)
        _backfill_owner_id(os.path.join("output", "series.json"), admin_id)
        os.makedirs("output", exist_ok=True)
        with open(marker, "w") as f:
            f.write("migrated")
        print("[migrate_auth_v1] Migration complete.")
    else:
        print("[migrate_auth_v1] Already migrated, skipping owner_id backfill.")


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest scripts/test_migrate_auth_v1.py -v`
Expected: PASS（3 tests）

- [ ] **Step 5: 本機實際跑一次遷移腳本驗證**

Run:
```
$env:PRISMREEL_ADMIN_EMAIL="admin@test.local"
$env:PRISMREEL_ADMIN_PASSWORD="devpassword123"
python scripts/migrate_auth_v1.py
```
Expected: 印出 `Created admin account` 或 `Migration complete`，`output/auth.db` 與 `output/.auth_migrated` 存在

- [ ] **Step 6: Commit**

```bash
git add scripts/migrate_auth_v1.py scripts/test_migrate_auth_v1.py
git commit -m "feat(auth): add idempotent auth migration script"
```

---

## Task 5: `models.py` 加 `owner_id` + Owned-Resource Dependencies

**Files:**
- Modify: `src/apps/comic_gen/models.py`
- Modify: `src/apps/comic_gen/api.py`
- Create: `src/apps/comic_gen/test_owned_resource.py`

**Interfaces:**
- Consumes: `pipeline.get_script`, `pipeline.get_series`（既有，pipeline.py:375/4277）, `auth.require_login`（Task 2）
- Produces:
  - `Script.owner_id: str`（models.py）
  - `Series.owner_id: str`（models.py）
  - `api.get_owned_script(script_id: str, user=Depends(auth.require_login)) -> Script`（FastAPI dependency，非本人非 admin 拋 404）
  - `api.get_owned_series(series_id: str, user=Depends(auth.require_login)) -> Series`（同上）

這兩個 dependency 是 Task 6/7 用來取代現有 60+ 端點手寫 `pipeline.get_script(script_id)` + 404 樣板的核心機制。

- [ ] **Step 1: 加 `owner_id` 欄位**

`src/apps/comic_gen/models.py` line 549 附近，`class Script(BaseModel):` 內加一行（放在 `id` 欄位之後）：

```python
    owner_id: str = Field(default="", description="User id that owns this project; empty string for pre-migration legacy records")
```

line 653 附近，`class Series(BaseModel):` 內同樣加：

```python
    owner_id: str = Field(default="", description="User id that owns this series")
```

`default=""` 而非必填，避免既有測試 fixture／未跑過遷移腳本的環境在 Pydantic 驗證時直接炸掉；遷移腳本負責把真實值填回去。

- [ ] **Step 2: 寫失敗測試**

`src/apps/comic_gen/test_owned_resource.py`:

```python
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def test_get_owned_script_returns_script_for_owner(monkeypatch):
    from src.apps.comic_gen import api
    from src.apps.comic_gen.models import Script

    fake_script = Script(id="s1", title="t", original_text="x", owner_id="user-1")
    monkeypatch.setattr(api.pipeline, "get_script", lambda sid: fake_script if sid == "s1" else None)

    class FakeUser:
        id = "user-1"
        role = "member"

    result = api.get_owned_script("s1", user=FakeUser())
    assert result.id == "s1"


def test_get_owned_script_404_for_non_owner(monkeypatch):
    from src.apps.comic_gen import api
    from src.apps.comic_gen.models import Script

    fake_script = Script(id="s1", title="t", original_text="x", owner_id="user-1")
    monkeypatch.setattr(api.pipeline, "get_script", lambda sid: fake_script if sid == "s1" else None)

    class OtherUser:
        id = "user-2"
        role = "member"

    with pytest.raises(HTTPException) as exc_info:
        api.get_owned_script("s1", user=OtherUser())
    assert exc_info.value.status_code == 404


def test_get_owned_script_admin_bypasses_ownership(monkeypatch):
    from src.apps.comic_gen import api
    from src.apps.comic_gen.models import Script

    fake_script = Script(id="s1", title="t", original_text="x", owner_id="user-1")
    monkeypatch.setattr(api.pipeline, "get_script", lambda sid: fake_script if sid == "s1" else None)

    class AdminUser:
        id = "admin-id"
        role = "admin"

    result = api.get_owned_script("s1", user=AdminUser())
    assert result.id == "s1"


def test_get_owned_script_404_when_not_found(monkeypatch):
    from src.apps.comic_gen import api

    monkeypatch.setattr(api.pipeline, "get_script", lambda sid: None)

    class AnyUser:
        id = "user-1"
        role = "member"

    with pytest.raises(HTTPException) as exc_info:
        api.get_owned_script("missing", user=AnyUser())
    assert exc_info.value.status_code == 404
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `pytest src/apps/comic_gen/test_owned_resource.py -v`
Expected: FAIL — `AttributeError: module 'src.apps.comic_gen.api' has no attribute 'get_owned_script'`

- [ ] **Step 4: 實作 dependency**

在 `api.py` 的 `pipeline = ComicGenPipeline()`（line 171）之後、Task 3 的 auth 端點之前插入：

```python
def get_owned_script(script_id: str, user=Depends(auth.require_login)):
    script = pipeline.get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Project not found")
    if user.role != "admin" and script.owner_id and script.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return script


def get_owned_series(series_id: str, user=Depends(auth.require_login)):
    series = pipeline.get_series(series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    if user.role != "admin" and series.owner_id and series.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Series not found")
    return series
```

`script.owner_id and script.owner_id != user.id` 這個判斷刻意讓空字串 `owner_id`（尚未跑遷移腳本的舊記錄）先放行——避免遷移腳本還沒執行時系統整個鎖死；正式部署時 Task 4 的遷移腳本會在啟動時自動回填，不會有長期存在空 `owner_id` 的正式資料。

- [ ] **Step 5: 執行測試確認通過**

Run: `pytest src/apps/comic_gen/test_owned_resource.py -v`
Expected: PASS（4 tests）

- [ ] **Step 6: Commit**

```bash
git add src/apps/comic_gen/models.py src/apps/comic_gen/api.py src/apps/comic_gen/test_owned_resource.py
git commit -m "feat(auth): add owner_id fields and owned-resource dependencies"
```

---

## Task 6: 套用 Owner 過濾 — Projects 端點（第一批）

**Files:**
- Modify: `src/apps/comic_gen/api.py`

**Interfaces:**
- Consumes: `get_owned_script`（Task 5）, `auth.require_login`（Task 2）

範圍：`POST /projects`（建立時寫入 owner_id）、`GET /projects/` (list，過濾)、`GET /projects/{script_id}`、`DELETE /projects/{script_id}`。這四個是最基礎的 CRUD，先驗證 dependency 注入模式在真實端點上可行，再在 Task 7 批次套用到剩餘 56+ 端點。

- [ ] **Step 1: 修改 `POST /projects`（api.py:409）寫入 owner_id**

找到現有 `create_project` 函式內建立 `Script(...)` 或呼叫 `pipeline.create_script(...)` 的那一行，加上 `owner_id=user.id` 參數；函式簽名加 `user=Depends(auth.require_login)`。

因為看不到 line 409-437 完整實作內容，執行本步驟前先 `Read src/apps/comic_gen/api.py` 該區間確認 `Script` 建立的確切呼叫方式，再對應修改建構參數，不要臆測欄位名稱。

- [ ] **Step 2: 修改 `GET /projects/`（api.py:493）加過濾**

```python
@app.get("/projects/", response_model=List[dict])
def list_projects(user=Depends(auth.require_login)):
    scripts = pipeline.scripts.values()
    if user.role != "admin":
        scripts = [s for s in scripts if not s.owner_id or s.owner_id == user.id]
    # 保留原本既有的 dict 轉換/排序邏輯，只在來源 iterable 前面插入這段過濾
    ...
```

先 Read 現有 `list_projects` 完整函式體，把過濾邏輯插入到原本 `pipeline.scripts.values()`（或等效寫法）被使用的地方，保留原有回傳格式不變。

- [ ] **Step 3: 修改 `GET /projects/{script_id}`（api.py:1451）改用 dependency**

```python
@app.get("/projects/{script_id}")
def get_project(script: Script = Depends(get_owned_script)):
    return signed_response(merged_project_payload(script))
```

- [ ] **Step 4: 修改 `DELETE /projects/{script_id}`（api.py:1465）改用 dependency**

```python
@app.delete("/projects/{script_id}")
def delete_project(script: Script = Depends(get_owned_script)):
    script_id = script.id
    try:
        if script.series_id:
            series = pipeline.get_series(script.series_id)
            if series and script_id in series.episode_ids:
                series.episode_ids.remove(script_id)
                pipeline._save_series_data()
        del pipeline.scripts[script_id]
        pipeline._save_data()
        return {"status": "deleted", "id": script_id, "title": script.title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 5: 手動驗證兩個帳號互相看不到對方專案**

先跑 Task 4 遷移腳本建立 admin，再透過 `POST /admin/invites` + `POST /auth/redeem_invite` 建立第二個 member 帳號（手動 curl 或 Python `requests` 腳本均可）。用兩組 cookie 分別呼叫 `POST /projects` 各建一個專案，再用帳號 B 的 cookie `GET /projects/{帳號A建立的id}`，確認回 404。

- [ ] **Step 6: Commit**

```bash
git add src/apps/comic_gen/api.py
git commit -m "feat(auth): apply owner filtering to core project CRUD endpoints"
```

---

## Task 7: 套用 Owner 過濾 — 剩餘全部 `{script_id}`/`{series_id}` 端點

**Files:**
- Modify: `src/apps/comic_gen/api.py`

**Interfaces:**
- Consumes: `get_owned_script`, `get_owned_series`（Task 5）

範圍：Task 6 未涵蓋的剩餘 56+ 個端點（`toggle_starred`、`reparse`、`extract_preview`、`generate_*`、`export`、`merge`、`frames/*`、`assets/*`、`characters`、`scenes`、`props`、`series` 相關端點等——完整清單見本檔案開頭 Grep 結果，或重新執行 `grep -n "@app\.\(get\|post\|delete\|put\)(\"/\(projects\|series\)" src/apps/comic_gen/api.py` 取得最新行號）。

這個任務因為端點數量多、每個函式簽名細節不同，**採取「逐端點確認再改」而非批次字串替換**——api.py 裡有些端點已經有其他 `Depends(...)` 或額外 path/body 參數，直接無腦替換簽名容易漏掉既有參數。

- [ ] **Step 1: 重新列出完整待改端點清單**

Run: `grep -n "^@app\.\(get\|post\|delete\|put\)(\"/\(projects\|series\)" src/apps/comic_gen/api.py`

比對 Task 6 已完成的 4 個，列出剩餘清單，逐一處理。

- [ ] **Step 2: 對每個 `{script_id}` 端點，統一改法**

原本模式：
```python
@app.post("/projects/{script_id}/xxx")
def some_handler(script_id: str, ...其他參數):
    script = pipeline.get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Project not found")
    ...函式主體使用 script_id 或 script...
```

改為：
```python
@app.post("/projects/{script_id}/xxx")
def some_handler(script: Script = Depends(get_owned_script), ...其他參數不變):
    script_id = script.id  # 若函式主體原本用 script_id 變數名，補這行相容
    ...函式主體不變...
```

若函式簽名裡 `script_id: str` 前面沒有其他 path 參數依賴它的位置順序，直接替換參數宣告即可；FastAPI 不依賴參數順序做路徑匹配。

若函式內部完全沒呼叫過 `pipeline.get_script(script_id)`（純粹只是路徑上有 `{script_id}` 但邏輯是查其他資料結構），先確認該端點是否真的操作 Script 資源，不要對不相關端點強加這個 dependency。

- [ ] **Step 3: 對每個 `{series_id}` 端點同理改用 `get_owned_series`**

- [ ] **Step 4: 全文 grep 確認無殘留手寫樣板**

Run: `grep -c "pipeline.get_script(script_id)" src/apps/comic_gen/api.py`
Expected: `0`（全部改用 dependency 注入；若有殘留，逐一確認是否為 Task 6/本步驟遺漏）

Run: `grep -c "pipeline.get_series(series_id)" src/apps/comic_gen/api.py`
Expected: `0`

- [ ] **Step 5: 語法檢查**

Run: `python -c "import ast; ast.parse(open('src/apps/comic_gen/api.py', encoding='utf-8').read())"`
Expected: 無錯誤

- [ ] **Step 6: 啟動 server 確認無 import/路由註冊錯誤**

Run:
```
$env:PRISMREEL_JWT_SECRET="dev-test-secret"
python -m uvicorn src.apps.comic_gen.api:app --port 17178
```
Expected: 正常啟動不報錯，`Ctrl+C` 停止

- [ ] **Step 7: 跑既有 pipeline 測試確認無迴歸**

Run: `pytest src/apps/comic_gen/test_pipeline.py src/apps/comic_gen/test_shared_asset_channels.py src/apps/comic_gen/test_shared_asset_pool.py -v`
Expected: 全數 PASS（這些測試若直接呼叫 pipeline 方法而非透過 API 層，不受本任務影響；若有測試直接呼叫受影響的 API handler function，需要更新測試也傳入 `user`/`script` 參數）

- [ ] **Step 8: Commit**

```bash
git add src/apps/comic_gen/api.py
git commit -m "feat(auth): apply owner filtering to all remaining project and series endpoints"
```

---

## Task 8: 檔案輸出路徑隔離 + `/files/users/` Middleware

**Files:**
- Modify: `src/apps/comic_gen/api.py`
- Modify: `src/apps/comic_gen/pipeline.py`（新專案輸出路徑）
- Create: `src/apps/comic_gen/test_file_ownership_middleware.py`

**Interfaces:**
- Consumes: `auth.get_current_user_from_cookie`（Task 2）

範圍：新建專案的衍生檔案（storyboard/assets/videos）落在 `output/users/{owner_id}/{project_id}/...`，並用 middleware 強制驗證存取者身分。**既有 `output/assets`、`output/video` 等全域路徑維持現狀**（Global Constraints 已載明），本任務只新增對新路徑格式的保護，不動舊路徑的掛載設定。

- [ ] **Step 1: 找到專案建立時決定輸出目錄的程式碼**

Run: `grep -n "output/assets\|output/storyboard\|output/video" src/apps/comic_gen/pipeline.py | head -20`

先確認 pipeline.py 裡哪個函式負責決定新專案檔案的儲存路徑（通常是 `create_script`/`create_project` 附近的路徑組裝邏輯），Read 該函式完整內容，不要臆測路徑組裝方式。

- [ ] **Step 2: 寫失敗測試（middleware 邏輯）**

`src/apps/comic_gen/test_file_ownership_middleware.py`:

```python
import pytest
from starlette.testclient import TestClient


def test_files_users_path_blocks_non_owner(monkeypatch):
    from src.apps.comic_gen import api

    class FakeUser:
        id = "user-2"
        role = "member"

    monkeypatch.setattr(api.auth, "get_current_user_from_cookie", lambda request: FakeUser())
    client = TestClient(api.app)
    resp = client.get("/files/users/user-1/some-project/frame.png")
    assert resp.status_code == 403


def test_files_users_path_allows_owner(monkeypatch, tmp_path):
    from src.apps.comic_gen import api
    import os

    os.makedirs("output/users/user-1/proj-x", exist_ok=True)
    with open("output/users/user-1/proj-x/test.txt", "w") as f:
        f.write("ok")

    class FakeUser:
        id = "user-1"
        role = "member"

    monkeypatch.setattr(api.auth, "get_current_user_from_cookie", lambda request: FakeUser())
    client = TestClient(api.app)
    resp = client.get("/files/users/user-1/proj-x/test.txt")
    assert resp.status_code == 200


def test_files_users_path_admin_bypasses(monkeypatch):
    from src.apps.comic_gen import api

    class AdminUser:
        id = "admin-id"
        role = "admin"

    monkeypatch.setattr(api.auth, "get_current_user_from_cookie", lambda request: AdminUser())
    client = TestClient(api.app)
    resp = client.get("/files/users/user-1/some-project/frame.png")
    assert resp.status_code != 403


def test_files_legacy_path_unaffected(monkeypatch):
    from src.apps.comic_gen import api
    client = TestClient(api.app)
    resp = client.get("/files/assets/does-not-exist.png")
    assert resp.status_code != 403
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `pytest src/apps/comic_gen/test_file_ownership_middleware.py -v`
Expected: FAIL（middleware 尚未存在，`test_files_users_path_blocks_non_owner` 會收到非 403 的回應）

- [ ] **Step 4: 新增靜態掛載與 middleware**

在 `api.py` 的既有 `app.mount("/files", ...)` 那組（line 155-167）之後加：

```python
os.makedirs("output/users", exist_ok=True)
app.mount("/files/users", StaticFiles(directory="output/users"), name="files_users")


@app.middleware("http")
async def enforce_file_ownership(request: Request, call_next):
    path = request.url.path
    if path.startswith("/files/users/"):
        parts = path.split("/")
        # ["", "files", "users", "{owner_id}", "{project_id}", ...]
        if len(parts) >= 4:
            owner_id = parts[3]
            user = auth.get_current_user_from_cookie(request)
            if not user or (user.role != "admin" and user.id != owner_id):
                return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)
```

放在既有 `add_cache_control_header` middleware（line 122）之後即可，中介層執行順序在此不影響邏輯正確性（各自檢查不同路徑前綴）。

- [ ] **Step 5: 修改 pipeline.py 新專案輸出路徑**

依 Step 1 找到的實際程式碼位置，把新建專案的路徑從全域 `output/assets/{project_id}/...` 改為 `output/users/{owner_id}/{project_id}/...`。此步驟需要 `owner_id` 傳入該函式——若目前函式簽名沒有這個參數，需要一併修改呼叫端（Task 6 的 `create_project` 端點）傳入。

- [ ] **Step 6: 執行測試確認通過**

Run: `pytest src/apps/comic_gen/test_file_ownership_middleware.py -v`
Expected: PASS（4 tests）

- [ ] **Step 7: Commit**

```bash
git add src/apps/comic_gen/api.py src/apps/comic_gen/pipeline.py src/apps/comic_gen/test_file_ownership_middleware.py
git commit -m "feat(auth): isolate new project file paths by owner with enforcement middleware"
```

---

## Task 9: `enforce_login` 全域 Middleware

**Files:**
- Modify: `src/apps/comic_gen/api.py`
- Create: `src/apps/comic_gen/test_enforce_login_middleware.py`

**Interfaces:**
- Consumes: `auth.get_current_user_from_cookie`, `auth.JWT_SECRET`（Task 1/2）

這是 spec §4.2 提到的最外層登入閘門——對非公開端點的請求，沒有有效 cookie 一律 401。跟 Task 5-8 的 per-resource dependency 不同層次：per-resource dependency 管「這個資源是不是你的」，這個 middleware 管「你有沒有登入」，兩者都需要。

- [ ] **Step 1: 寫失敗測試**

`src/apps/comic_gen/test_enforce_login_middleware.py`:

```python
import pytest
from starlette.testclient import TestClient


def test_protected_endpoint_401_without_cookie(monkeypatch):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret")
    import importlib
    from src.apps.comic_gen import api
    importlib.reload(api)

    client = TestClient(api.app)
    resp = client.get("/projects/")
    assert resp.status_code == 401


def test_auth_login_endpoint_accessible_without_cookie(monkeypatch):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret")
    import importlib
    from src.apps.comic_gen import api
    importlib.reload(api)

    client = TestClient(api.app)
    resp = client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
    assert resp.status_code != 401 or resp.json().get("detail") != "Not authenticated"


def test_health_endpoint_accessible_without_cookie(monkeypatch):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret")
    import importlib
    from src.apps.comic_gen import api
    importlib.reload(api)

    client = TestClient(api.app)
    resp = client.get("/health")
    assert resp.status_code != 401


def test_login_gate_disabled_when_jwt_secret_unset(monkeypatch):
    monkeypatch.delenv("PRISMREEL_JWT_SECRET", raising=False)
    import importlib
    from src.apps.comic_gen import api, auth
    importlib.reload(auth)
    importlib.reload(api)

    client = TestClient(api.app)
    resp = client.get("/projects/")
    assert resp.status_code != 401
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest src/apps/comic_gen/test_enforce_login_middleware.py -v`
Expected: FAIL（目前 `/projects/` 沒有全域登入閘門，僅靠 Task 6 加的 `Depends(auth.require_login)`——但那是每個端點各自宣告，尚未有「未宣告的端點自動要求登入」這個全域行為，先確認實際失敗訊息再繼續）

- [ ] **Step 3: 實作 middleware**

在 `api.py` 加：

```python
_AUTH_PUBLIC_PREFIXES = ("/health", "/files/", "/static/", "/docs", "/openapi.json", "/redoc", "/auth/login", "/auth/redeem_invite")


@app.middleware("http")
async def enforce_login(request: Request, call_next):
    if not auth.JWT_SECRET:
        return await call_next(request)
    path = request.url.path
    if path.startswith(_AUTH_PUBLIC_PREFIXES):
        return await call_next(request)
    user = auth.get_current_user_from_cookie(request)
    if user is None or not user.is_active:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return await call_next(request)
```

放在既有 `enforce_api_key` middleware（line 97）之後，維持「先過 API Key 這道薄閘，再過登入驗證」的既定分層（spec §4.2）。

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest src/apps/comic_gen/test_enforce_login_middleware.py -v`
Expected: PASS（4 tests）

- [ ] **Step 5: 跑全部後端測試套件確認無迴歸**

Run: `pytest src/apps/comic_gen/ -v`
Expected: 全數 PASS

- [ ] **Step 6: Commit**

```bash
git add src/apps/comic_gen/api.py src/apps/comic_gen/test_enforce_login_middleware.py
git commit -m "feat(auth): add global enforce_login middleware gated by PRISMREEL_JWT_SECRET"
```

---

## Task 10: 前端 — axios 全域設定 + 401 攔截

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/authInterceptor.ts`

**Interfaces:**
- Produces: `authInterceptor.installAuthInterceptor() -> void`（在 app 啟動時呼叫一次，註冊 axios response interceptor）

因為專案沒有共用 `axios.create()` instance（全域直接用 `axios.xxx`），採用 `axios.defaults` 設定，不重構成 instance（避免牽動 100+ 處呼叫點）。

- [ ] **Step 1: 在 `api.ts` 加 `withCredentials`**

`frontend/src/lib/api.ts` 找到現有：
```typescript
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;
if (API_KEY) {
    axios.defaults.headers.common["X-API-Key"] = API_KEY;
}
```
在這段之後加一行：
```typescript
axios.defaults.withCredentials = true;
```

- [ ] **Step 2: 新增 401 攔截器模組**

`frontend/src/lib/authInterceptor.ts`:

```typescript
import axios from "axios";

let installed = false;

export function installAuthInterceptor() {
    if (installed) return;
    installed = true;
    axios.interceptors.response.use(
        (response) => response,
        (error) => {
            if (error?.response?.status === 401 && typeof window !== "undefined") {
                if (!window.location.pathname.startsWith("/login")) {
                    window.location.href = "/login";
                }
            }
            return Promise.reject(error);
        }
    );
}
```

- [ ] **Step 3: 在根 layout 呼叫安裝函式**

Run: `grep -n "\"use client\"\|export default function" frontend/src/app/layout.tsx`

先確認 `frontend/src/app/layout.tsx` 是否為 client component；若是 server component（Next.js App Router 預設），需要在最外層 client 元件（通常是既有的某個 providers wrapper）內用 `useEffect` 呼叫，而不是直接在 module 層級呼叫（SSR 階段沒有 `window`）。找到現有 client-side 初始化邏輯的位置（例如既有的 store 初始化 `useEffect`），在同樣位置加：

```typescript
useEffect(() => {
    installAuthInterceptor();
}, []);
```

- [ ] **Step 4: 手動驗證**

啟動前端 dev server（`npm run dev`），開瀏覽器 devtools Network tab，人工觸發一個會回 401 的 API 呼叫（例如先不登入直接訪問受保護頁面），確認被導向 `/login`（此步驟需等 Task 11 登入頁存在才能完整驗證，先確認 interceptor 註冊本身不報錯即可）。

Run: `npm run typecheck`
Expected: 無型別錯誤

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/authInterceptor.ts frontend/src/app/layout.tsx
git commit -m "feat(auth): add global withCredentials and 401 redirect interceptor"
```

---

## Task 11: 前端 — 登入頁 + 邀請落地頁

**Files:**
- Create: `frontend/src/app/login/page.tsx`
- Create: `frontend/src/app/redeem/[code]/page.tsx`
- Modify: `frontend/src/lib/api.ts`（加 auth 相關 API 呼叫函式）

**Interfaces:**
- Consumes: `POST /auth/login`, `POST /auth/redeem_invite`（Task 3）
- Produces: `api.login(email, password) -> Promise<{id, email, role, display_name}>`, `api.redeemInvite(code, email, password) -> Promise<{id, email, role}>`

- [ ] **Step 1: 在 `api.ts` 加 auth API 函式**

在檔案內既有的 export 函式群組附近加：

```typescript
export async function login(email: string, password: string) {
    const res = await axios.post(`${API_URL}/auth/login`, { email, password });
    return res.data;
}

export async function redeemInvite(code: string, email: string, password: string) {
    const res = await axios.post(`${API_URL}/auth/redeem_invite`, { invite_code: code, email, password });
    return res.data;
}

export async function logout() {
    await axios.post(`${API_URL}/auth/logout`);
}

export async function getCurrentUser() {
    const res = await axios.get(`${API_URL}/auth/me`);
    return res.data;
}
```

- [ ] **Step 2: 建立登入頁**

`frontend/src/app/login/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

export default function LoginPage() {
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            await login(email, password);
            router.push("/");
        } catch (err) {
            setError("帳號或密碼錯誤");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--color-bg, #1a1815)" }}>
            <form onSubmit={handleSubmit} className="glass-panel atelier-card p-8 w-full max-w-sm space-y-4">
                <h1 className="text-2xl font-display">PrismReel Studio</h1>
                <div>
                    <label className="block text-sm mb-1">Email</label>
                    <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        className="w-full px-3 py-2 rounded border"
                    />
                </div>
                <div>
                    <label className="block text-sm mb-1">密碼</label>
                    <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        className="w-full px-3 py-2 rounded border"
                    />
                </div>
                {error && <p className="text-sm text-red-500">{error}</p>}
                <button type="submit" disabled={loading} className="w-full py-2 rounded bg-black text-white">
                    {loading ? "登入中..." : "登入"}
                </button>
            </form>
        </div>
    );
}
```

- [ ] **Step 3: 建立邀請落地頁**

`frontend/src/app/redeem/[code]/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { redeemInvite } from "@/lib/api";

export default function RedeemInvitePage() {
    const router = useRouter();
    const params = useParams();
    const code = params.code as string;
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            await redeemInvite(code, email, password);
            router.push("/");
        } catch (err: any) {
            setError(err?.response?.data?.detail || "邀請碼無效或已使用");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--color-bg, #1a1815)" }}>
            <form onSubmit={handleSubmit} className="glass-panel atelier-card p-8 w-full max-w-sm space-y-4">
                <h1 className="text-2xl font-display">建立帳號</h1>
                <div>
                    <label className="block text-sm mb-1">Email</label>
                    <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="w-full px-3 py-2 rounded border" />
                </div>
                <div>
                    <label className="block text-sm mb-1">設定密碼</label>
                    <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required className="w-full px-3 py-2 rounded border" />
                </div>
                {error && <p className="text-sm text-red-500">{error}</p>}
                <button type="submit" disabled={loading} className="w-full py-2 rounded bg-black text-white">
                    {loading ? "建立中..." : "建立帳號"}
                </button>
            </form>
        </div>
    );
}
```

- [ ] **Step 4: Typecheck**

Run: `npm run typecheck`
Expected: 無錯誤

- [ ] **Step 5: 手動視覺驗收**

啟動前端+後端（後端需先設好 `PRISMREEL_JWT_SECRET`/`PRISMREEL_ADMIN_EMAIL`/`PRISMREEL_ADMIN_PASSWORD` 並跑過 Task 4 遷移腳本），瀏覽器開 `http://localhost:3000/login`，Playwright 截圖確認 Atelier 視覺風格套用正確（暖深石墨底 + 玻璃面板 + Fraunces 標題字），輸入正確帳密後導向首頁。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/login frontend/src/app/redeem frontend/src/lib/api.ts
git commit -m "feat(auth): add login page and invite redemption page"
```

---

## Task 12: 前端 — Admin 後台 + 側欄登出按鈕

**Files:**
- Create: `frontend/src/app/admin/users/page.tsx`
- Modify: `frontend/src/components/layout/GlobalSidebar.tsx`（或該目錄下實際負責側欄的檔案，先 Read 確認檔名）
- Modify: `frontend/src/lib/api.ts`（加 admin API 呼叫函式）

**Interfaces:**
- Consumes: `GET /admin/users`, `POST /admin/invites`, `POST /admin/users/{id}/reset_password`, `POST /admin/users/{id}/deactivate`（Task 3）, `logout`（Task 11）

- [ ] **Step 1: 確認側欄實際檔案與既有設定齒輪按鈕位置**

Run: `grep -rn "Settings\|齒輪\|gear" frontend/src/components/layout/ --include="*.tsx" -l`

Read 該檔案找到既有設定按鈕的 JSX 位置與樣式 class，登出按鈕要沿用同樣的視覺模式（Global Constraints 未特別規定，但 spec §5 要求「沿用既有設定齒輪的視覺位置模式」）。

- [ ] **Step 2: 在 `api.ts` 加 admin API 函式**

```typescript
export async function adminListUsers() {
    const res = await axios.get(`${API_URL}/admin/users`);
    return res.data;
}

export async function adminCreateInvite(role: string = "member", emailHint?: string) {
    const res = await axios.post(`${API_URL}/admin/invites`, { role, email_hint: emailHint });
    return res.data;
}

export async function adminResetPassword(userId: string, newPassword: string) {
    const res = await axios.post(`${API_URL}/admin/users/${userId}/reset_password`, { new_password: newPassword });
    return res.data;
}

export async function adminDeactivateUser(userId: string) {
    const res = await axios.post(`${API_URL}/admin/users/${userId}/deactivate`);
    return res.data;
}
```

- [ ] **Step 3: 建立 admin 後台頁**

`frontend/src/app/admin/users/page.tsx`:

```tsx
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { adminListUsers, adminCreateInvite, adminResetPassword, adminDeactivateUser, getCurrentUser } from "@/lib/api";

type AdminUser = {
    id: string;
    email: string;
    role: string;
    display_name: string | null;
    is_active: boolean;
    created_at: number;
};

export default function AdminUsersPage() {
    const router = useRouter();
    const [users, setUsers] = useState<AdminUser[]>([]);
    const [inviteLink, setInviteLink] = useState("");
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        getCurrentUser()
            .then((me) => {
                if (me.role !== "admin") {
                    router.push("/");
                    return;
                }
                return adminListUsers();
            })
            .then((data) => {
                if (data) setUsers(data);
            })
            .finally(() => setLoading(false));
    }, [router]);

    async function handleCreateInvite() {
        const { invite_code } = await adminCreateInvite();
        setInviteLink(`${window.location.origin}/redeem/${invite_code}`);
    }

    async function handleResetPassword(userId: string) {
        const newPassword = window.prompt("輸入新密碼");
        if (!newPassword) return;
        await adminResetPassword(userId, newPassword);
        window.alert("密碼已重設");
    }

    async function handleDeactivate(userId: string) {
        if (!window.confirm("確定停用此帳號？")) return;
        await adminDeactivateUser(userId);
        const data = await adminListUsers();
        setUsers(data);
    }

    if (loading) return <div className="p-8">載入中...</div>;

    return (
        <div className="p-8 space-y-6">
            <h1 className="text-2xl font-display">使用者管理</h1>
            <button onClick={handleCreateInvite} className="px-4 py-2 rounded bg-black text-white">
                建立邀請連結
            </button>
            {inviteLink && (
                <div className="glass-panel p-4 text-sm break-all">{inviteLink}</div>
            )}
            <table className="w-full text-sm">
                <thead>
                    <tr className="text-left">
                        <th>Email</th>
                        <th>角色</th>
                        <th>狀態</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    {users.map((u) => (
                        <tr key={u.id}>
                            <td>{u.email}</td>
                            <td>{u.role}</td>
                            <td>{u.is_active ? "啟用" : "停用"}</td>
                            <td className="space-x-2">
                                <button onClick={() => handleResetPassword(u.id)}>重設密碼</button>
                                {u.is_active && (
                                    <button onClick={() => handleDeactivate(u.id)}>停用</button>
                                )}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
```

- [ ] **Step 4: 加登出按鈕到側欄**

依 Step 1 找到的實際檔案，在既有設定齒輪按鈕上方加：

```tsx
<button onClick={async () => { await logout(); window.location.href = "/login"; }} title="登出">
    <LogOut size={18} />
</button>
```

需從 `lucide-react` import `LogOut`，從 `@/lib/api` import `logout`。實際 JSX 縮排/class 要比照該檔案既有按鈕的寫法，先 Read 完整上下文再插入，不要臆測既有 class 名稱。

- [ ] **Step 5: Typecheck + Lint**

Run: `npm run typecheck && npm run lint`
Expected: 無錯誤

- [ ] **Step 6: 手動驗收**

用 admin 帳號登入，Playwright 截圖確認 `/admin/users` 頁面正常顯示使用者清單，建立邀請連結後用無痕視窗開啟該連結完成註冊流程，回到 admin 頁確認新使用者出現在清單。用 member 帳號登入後嘗試訪問 `/admin/users`，確認被導回首頁。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/admin frontend/src/lib/api.ts frontend/src/components/layout/
git commit -m "feat(auth): add admin user management page and sidebar logout button"
```

---

## Task 13: 部署設定 — `.env.example`、Dockerfile 遷移腳本掛鉤、`docker-compose.yml`

**Files:**
- Modify: `.env.example`
- Modify: `Dockerfile.backend`

**Interfaces:**
- 無新程式碼介面，純部署設定

- [ ] **Step 1: 更新 `.env.example`**

在既有「安全配置」區塊後面加一個新區塊：

```
# ===============================
# 多租戶登入系統（2026-09-08 新增）
# ===============================
# JWT 簽章密鑰，多用戶部署必填；留空 = 完全停用登入閘門（desktop 單機模式行為）。
# 正式環境務必用高熵隨機字串，例如: openssl rand -hex 32
PRISMREEL_JWT_SECRET=

# 首次啟動遷移腳本用來建立預設 admin 帳號，僅在 output/auth.db 尚無任何使用者時生效。
PRISMREEL_ADMIN_EMAIL=
PRISMREEL_ADMIN_PASSWORD=

# JWT 有效天數，選填，預設 7。
PRISMREEL_JWT_EXPIRE_DAYS=7
```

- [ ] **Step 2: 修改 `Dockerfile.backend` 的 CMD 插入遷移腳本**

`Dockerfile.backend` 目前：
```dockerfile
CMD ["python", "-m", "uvicorn", "src.apps.comic_gen.api:app", "--host", "0.0.0.0", "--port", "17177"]
```

改為 shell 形式，先跑遷移腳本再啟動 uvicorn（遷移腳本失敗時容器應該啟動失敗，不能吞掉錯誤靜默繼續）：

```dockerfile
COPY scripts/migrate_auth_v1.py scripts/migrate_auth_v1.py

CMD python scripts/migrate_auth_v1.py && python -m uvicorn src.apps.comic_gen.api:app --host 0.0.0.0 --port 17177
```

`COPY scripts/migrate_auth_v1.py scripts/migrate_auth_v1.py` 要放在既有 `COPY src/ src/`（line 15）之後。

- [ ] **Step 3: 本機 Docker build 驗證（不 push、不動 VPS）**

Run: `docker build -f Dockerfile.backend -t prismreel-backend-auth-test .`
Expected: build 成功

- [ ] **Step 4: 本機 docker run 驗證遷移腳本會擋下缺環境變數的啟動**

Run: `docker run --rm prismreel-backend-auth-test`（不帶任何 env）
Expected: 容器印出 `PRISMREEL_ADMIN_EMAIL and PRISMREEL_ADMIN_PASSWORD must be set` 並以非 0 exit code 結束

- [ ] **Step 5: 本機 docker run 驗證帶正確環境變數能正常啟動**

Run: `docker run --rm -e PRISMREEL_JWT_SECRET=test -e PRISMREEL_ADMIN_EMAIL=admin@test.local -e PRISMREEL_ADMIN_PASSWORD=testpw123 -p 17178:17177 prismreel-backend-auth-test`
Expected: 印出遷移成功訊息，接著 uvicorn 正常啟動監聽

- [ ] **Step 6: Commit**

```bash
git add .env.example Dockerfile.backend
git commit -m "chore(auth): wire migration script into container startup and document new env vars"
```

---

## Task 14: 上線部署（VPS）

**這個任務不寫程式碼，是實際上線操作步驟**，執行者需要 SSH 存取 `vps_main`（202.182.117.182）。**執行前務必再次確認 Task 1-13 全部本機測試綠燈，且已跟使用者確認要上線的時間點**——這一步會影響 https://prismreel.soulo-ai.com 正式站台。

- [ ] **Step 1: SCP 同步最新程式碼到 VPS**

依照 `feedback_git_push_does_not_deploy_manual_vps_sync_required.md` 記載的既有同步方式（git push 不會自動部署，VPS 是手動複製非 git clone），把本機最新的 `src/`、`scripts/`、`frontend/`、`Dockerfile.backend`、`docker-compose.yml`、`requirements*.txt` 同步到 `vps_main:/opt/prismreel`。

- [ ] **Step 2: 在 VPS 的 `.env` 手動加新環境變數**

SSH 進 `vps_main`，編輯 `/opt/prismreel/.env`，加入：
```
PRISMREEL_JWT_SECRET=<openssl rand -hex 32 產生的值>
PRISMREEL_ADMIN_EMAIL=<實際管理員信箱>
PRISMREEL_ADMIN_PASSWORD=<高強度密碼>
```

- [ ] **Step 3: Docker rebuild**

```bash
cd /opt/prismreel
docker compose build backend frontend
docker compose up -d
```

- [ ] **Step 4: 檢查容器啟動日誌確認遷移腳本成功**

```bash
docker compose logs backend --tail 50
```
Expected: 看到 `[migrate_auth_v1] Created admin account` 或 `Migration complete`，接著 uvicorn 正常啟動訊息，沒有 exit code 非 0 的紀錄

- [ ] **Step 5: Live 驗證（等 60 秒快取生效後）**

```bash
curl -s -o /dev/null -w "%{http_code}" https://prismreel.soulo-ai.com/login
curl -s -X POST https://prismreel.soulo-ai.com/auth/login -H "Content-Type: application/json" -d "{\"email\":\"wrong@test.com\",\"password\":\"wrong\"}"
```
Expected: `/login` 回 200；`/auth/login` 用錯誤帳密回 401 + `{"detail":"帳號或密碼錯誤"}`

- [ ] **Step 6: 瀏覽器實際登入驗證**

用剛設定的 admin 帳密登入 https://prismreel.soulo-ai.com，確認能看到既有專案（遷移腳本已把舊資料歸給這個 admin 帳號），Playwright 截圖存證。

- [ ] **Step 7: 建立第一個邀請連結給實際會用到的使用者**

用 admin 後台建立邀請連結，交給實際使用者完成註冊，確認新帳號登入後看不到 admin 的既有專案（資料隔離生效）。

---

## Self-Review 記錄

**Spec 覆蓋檢查：**
- §2 核心決策 8 項 → Task 1-13 全數對應（JWT+Cookie=Task1/3，SQLite=Task1，邀請制=Task2/3，舊資料歸admin=Task4，全域資產庫不隔離=未新增任何 GlobalAssetLibrary 改動，符合「不加owner_id」，密碼重設非自助=Task3 admin-only 端點，Atelier視覺=Task11）
- §3 資料模型 → Task 1（schema）、Task 5（owner_id 欄位）、Task 8（檔案路徑，含與 spec 落差的記錄）
- §3.5 遷移腳本 → Task 4
- §4 API 設計 → Task 3（新端點）、Task 6-7（既有端點過濾）、Task 9（全域登入閘門）
- §5 前端 → Task 10（axios/攔截）、Task 11（登入頁/邀請頁）、Task 12（admin/登出）
- §6 錯誤處理 → Task 3（統一錯誤訊息）、Task 10（401攔截）
- §7 測試策略 → 各 Task 內建 TDD 步驟 + Task 11/12 手動 Playwright 驗收
- §8 部署與回滾 → Task 13（.env.example/Dockerfile）、Task 14（VPS上線）；回滾機制（移除 JWT_SECRET=停用登入）已在 Task 9 middleware 邏輯中原生支援，無需額外任務

**與 spec 的已知落差（已在對應 Task 內記錄理由）：**
1. `/files/` 舊全域路徑不做強制驗證（Task 8）——spec 原文暗示全面隔離，但 StaticFiles 掛載機制無 hook 點，且改動既有全域路徑會影響大量既有前端引用；新路徑 `/files/users/` 有 middleware 強制驗證，舊路徑風險已知並記錄。
2. owner 過濾範圍從 spec 描述的「既有端點」明確化為「全部 60+ 個 `{script_id}`/`{series_id}` 端點」，並收斂成兩個共用 dependency 而非逐端點手寫判斷——這是規模確認後的實作策略決定，已與使用者確認採用一次到位方案。

**Placeholder 掃描：** 全文搜尋「TBD」「TODO」「待補」「類似 Task」— 無殘留。Task 6/7/8/12 有幾處標記「先 Read 確認實際程式碼再改」，這是因為對應區塊行號已知但完整函式體未在本次規劃中逐行讀出，屬於執行時的具體查證步驟而非缺內容的佔位符。

**型別一致性：** `get_owned_script`/`get_owned_series` 命名與回傳型別在 Task 5 定義、Task 6/7/8 使用時一致；`User`（dataclass，Task 2）與 FastAPI dependency 回傳的物件在 Task 3/5/8/9 中屬性存取（`.id`/`.role`/`.is_active`）保持一致。
