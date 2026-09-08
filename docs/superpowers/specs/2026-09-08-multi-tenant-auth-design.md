# 多租戶帳號登入系統設計

> 狀態：待使用者審閱
> 日期：2026-09-08
> 範圍：`prismreel.soulo-ai.com`（Docker Compose 部署版），desktop 單機模式（`python main.py`）不受影響

## 1. 背景與目標

目前後端（FastAPI）沒有任何登入機制，唯一的防護是可選的 `PRISMREEL_API_KEY` 門禁（打包進前端 bundle，只能擋外部隨機掃描，防不了已能打開頁面的人）。所有資料存在單一全域 JSON 檔（`output/projects.json`、`series.json`、`library_assets.json`），沒有 `user_id` 概念，任何能打開頁面的人都能看到全部專案、消耗 AI 供應商付費額度。

目標：把 `prismreel.soulo-ai.com` 改造成多用戶 SaaS——每個使用者登入後只看得到自己的專案/系列，彼此資料互相隔離；建帳走邀請制（僅管理員能建立新帳號），不開放自助註冊。

Desktop 單機模式（`main.py`，`127.0.0.1` 本機執行）維持現狀不變——認證 middleware 只在偵測到多用戶部署情境時啟用，不影響現有單機使用者的既有工作流程。

## 2. 核心決策（已與使用者確認）

| 決策點 | 選擇 | 理由 |
|---|---|---|
| 使用情境 | 多用戶 SaaS 化 | 未來會給多個外部使用者各自使用 |
| 隔離範圍 | 一次到位：登入 + 多租戶資料隔離 | 避免先上線登入、後續發現資料互相污染再回頭改資料模型 |
| 註冊方式 | 邀請制／管理員建帳 | 現階段少數已知使用者的封閉現況 |
| Session 策略 | JWT + HttpOnly Cookie | SPA + 單體部署場景不需要 Authorization Header 的跨域彈性；HttpOnly 擋 XSS 竊取 token |
| 資料儲存 | 新增 SQLite（`auth.db`） | 零額外服務依賴，與現有 Docker 單容器部署相容 |
| 舊資料遷移 | 全部歸到一個預設建立的 admin 帳號 | 不遺失現有 `output/projects.json` 等既有作品 |
| 全域資產庫（`library_assets.json`） | **維持全域共享**，不隨 user_id 隔離 | 使用者明確要求；記錄取捨：這與「多租戶隔離」目標存在張力——若日後任兩個租戶互不信任，共享資產庫會讓彼此看到對方上傳的角色/場景/道具。目前使用者評估此風險可接受 |
| 密碼重設 | 不做自助流程，管理員手動於後台重設 | 邀請制小規模場景，避免引入 SMTP 外部依賴 |
| 登入頁視覺 | 套用 Line B Atelier 設計語言 | 與現有產品視覺一致 |

## 3. 資料模型

### 3.1 新增 SQLite 資料庫 `output/auth.db`

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,              -- uuid4 hex
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,      -- bcrypt
    role TEXT NOT NULL DEFAULT 'member',  -- 'admin' | 'member'
    display_name TEXT,
    created_at REAL NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE invites (
    code TEXT PRIMARY KEY,            -- 隨機 token，作為邀請連結參數
    created_by TEXT NOT NULL REFERENCES users(id),
    email_hint TEXT,                  -- 選填，建立邀請時預先指定要給誰用
    role TEXT NOT NULL DEFAULT 'member',
    created_at REAL NOT NULL,
    used_at REAL,
    used_by TEXT REFERENCES users(id)
);
```

放在 `output/` 目錄下（跟 `projects.json` 同層），沿用既有 volume mount（`docker-compose.yml` 已把 `./output:/app/output` 掛載），不需要新增 volume 設定。

### 3.2 既有資料模型加 `owner_id`

`src/apps/comic_gen/models.py`：
- `Script`（`class Script(BaseModel)`，line 549）新增 `owner_id: str` 欄位
- `Series`（line 653）新增 `owner_id: str` 欄位
- `GlobalAssetLibrary`（line 699）**不加** `owner_id`（維持全域共享，決策見上表）

### 3.3 `pipeline.py` 過濾邏輯

`ComicGenPipeline` 目前用 `self.scripts: Dict[str, Script]`、`self.series_store: Dict[str, Series]` 在記憶體裡存全量資料，讀寫都走 `self.data_file`（單一 JSON）。改動策略：

- **不拆檔案**：仍是一份 `output/projects.json`，每筆記錄帶 `owner_id`，避免多檔案 I/O 複雜化併發鎖（現有 `self._save_lock` 邏輯不變）
- **在 API 層過濾**，不在 `pipeline.py` 內部過濾：`pipeline.py` 的方法簽章不變，改為在 `api.py` 的路由函式裡，取出當前登入者的 `user_id` 後過濾 `pipeline.scripts.values()` / `pipeline.series_store.values()`，並在建立新 project/series 時寫入 `owner_id = current_user.id`
- 原因：`pipeline.py` 已經是一個沒有請求上下文概念的純業務邏輯層（給桌面模式共用），把 `user_id` 概念推進去會污染桌面單機模式的呼叫介面；隔離放在 API 層邊界最乾淨

### 3.4 檔案輸出路徑隔離

`output/assets/`、`output/storyboard/`、`output/outputs/videos/` 等目前是全域共用路徑，任何人猜到檔名都能存取（`/files/` 路徑在 API Key 豁免清單內）。改為：

- 新專案建立時，該專案所有衍生檔案落在 `output/users/{owner_id}/{project_id}/...` 下
- `/files/` 靜態掛載路由改成需要驗證 `owner_id` 與請求者相符才能存取（唯一例外：admin 角色可存取全部路徑，供後台管理用）
- 既有全域路徑下的舊檔案不搬動，靠 3.5 的遷移腳本把舊 project 的 `owner_id` 全指到 admin，讀取時走舊路徑相容層（`to_project_media_ref` 這類既有 helper 已在處理路徑正規化，沿用）

### 3.5 遷移腳本

新增 `scripts/migrate_auth_v1.py`，冪等、可重複執行：

1. 若 `output/auth.db` 不存在則建立 schema
2. 若 `users` 表為空：
   - 建立一個 admin 帳號，email/密碼從環境變數 `PRISMREEL_ADMIN_EMAIL` / `PRISMREEL_ADMIN_PASSWORD` 讀取（部署時由操作者指定，避免寫死預設密碼進版本庫）
   - 若未設定則腳本報錯中止，提示先設定這兩個環境變數
3. 讀取 `output/projects.json`、`series.json`：對每筆缺少 `owner_id` 的記錄，補上 admin 的 `user_id`，寫回檔案
4. 記錄一個 marker 檔 `output/.auth_migrated`，避免重複執行時重新覆蓋已手動調整過的 `owner_id`

`Dockerfile.backend` 的啟動腳本在 `uvicorn` 啟動前執行這支遷移腳本一次。

## 4. 後端 API 設計

新增模組 `src/apps/comic_gen/auth.py`：

- `hash_password` / `verify_password`（bcrypt，透過 `passlib`）
- `create_access_token(user_id, role) -> str`（PyJWT，密鑰讀 `PRISMREEL_JWT_SECRET` 環境變數，HS256，效期預設 7 天）
- `get_current_user`（FastAPI dependency）：從 request cookie 讀 `access_token`，驗簽失敗回 401
- `require_admin`（FastAPI dependency，疊加在 `get_current_user` 之上）：`role != 'admin'` 回 403

### 4.1 新增端點

| 方法 | 路徑 | 說明 | 權限 |
|---|---|---|---|
| POST | `/auth/login` | body: email+password；成功則 `Set-Cookie: access_token=...; HttpOnly; Secure; SameSite=Lax` | 公開 |
| POST | `/auth/logout` | 清除 cookie | 需登入 |
| GET | `/auth/me` | 回傳當前使用者 email/role/display_name | 需登入 |
| POST | `/auth/redeem_invite` | body: invite_code+email+password；建立帳號並標記邀請碼已用 | 公開（需有效邀請碼） |
| POST | `/admin/invites` | 建立新邀請碼 | admin |
| GET | `/admin/users` | 列出所有使用者 | admin |
| POST | `/admin/users/{id}/reset_password` | 管理員手動重設指定使用者密碼 | admin |
| POST | `/admin/users/{id}/deactivate` | 停用帳號（`is_active=0`），保留其歷史專案不刪除 | admin |

### 4.2 既有端點改動

- `enforce_api_key` middleware（`api.py:98`）之後、原有路由邏輯之前，加一道 `enforce_login` middleware：對非 `_API_KEY_EXEMPT_PREFIXES` 且非 `/auth/*` 公開端點的請求，要求有效 cookie，否則 401
- 所有 `POST /projects`、`GET /projects`、`GET /projects/{id}` 等既有端點內部改為依 `current_user.id` 過濾/綁定 `owner_id`；非 owner 存取他人 `project_id` 回 404（不回 403，避免洩漏「此 ID 存在但不屬於你」的資訊）
- `PRISMREEL_API_KEY` 門禁維持不變、疊加在最外層（雙層防護：先過 API Key 這道薄閘，再過登入驗證）

### 4.3 環境變數新增

```
PRISMREEL_JWT_SECRET=           # 必填於多用戶部署；留空則啟動時報錯拒絕啟動（避免用預設弱密鑰上線）
PRISMREEL_ADMIN_EMAIL=          # 首次遷移腳本用來建立 admin 帳號
PRISMREEL_ADMIN_PASSWORD=       # 同上
PRISMREEL_JWT_EXPIRE_DAYS=7     # 選填，預設 7
```

## 5. 前端改動

- 新增 `frontend/src/app/login/page.tsx`：套用 Line B Atelier 風格（`.atelier-card` 玻璃面板 + 暖深石墨底色 + Fraunces 衬線標題），email+password 表單
- `frontend/src/lib/api.ts` 的 axios instance 加 `withCredentials: true`（cookie 隨請求送出）；新增一個 axios response interceptor：收到 401 時導向 `/login`
- `GlobalSidebar`（`frontend/src/components/layout/`）底部新增登出按鈕（沿用既有設定齒輪的視覺位置模式，齒輪上方加一個登出圖示）
- 新增 `frontend/src/app/admin/users/page.tsx`：admin-only 後台頁，列表 + 建立邀請碼 + 重設密碼按鈕；非 admin 角色訪問時前端路由守衛直接導回工作區首頁（後端 `/admin/*` 仍是最終防線）
- 新增 `frontend/src/app/redeem/[code]/page.tsx`：邀請連結落地頁，輸入 email+password 完成註冊

## 6. 錯誤處理

- 登入失敗（帳密錯誤）：統一回「帳號或密碼錯誤」，不區分是 email 不存在還是密碼錯，避免帳號枚舉
- JWT 過期：前端攔截 401 導回登入頁，並清空前端記憶體中的使用者狀態（Zustand store）
- 邀請碼無效/已使用：`/auth/redeem_invite` 回 400，前端顯示明確錯誤文字
- 遷移腳本缺少必要環境變數：直接讓容器啟動失敗並印出清楚訊息，不允許"靜默用預設密碼"這種不安全的 fallback

## 7. 測試策略

- 後端：`pytest` 新增 `test_auth.py`——登入成功/失敗、JWT 過期驗證、`owner_id` 過濾正確性（使用者 A 建立的 project 對使用者 B 呼叫 `GET /projects/{id}` 回 404）、admin 端點權限檢查
- 遷移腳本：`test_migrate_auth_v1.py`——冪等性（跑兩次不重複建立 admin、不覆蓋已存在的 `owner_id`）
- 前端：現有 `npm run test:all` 涵蓋範圍內新增登入頁渲染測試、401 攔截導向測試
- 手動驗收：Playwright 截圖驗證登入頁 Atelier 視覺、瀏覽器測試 A/B 兩個帳號互相看不到對方專案

## 8. 部署與回滾

- 新增環境變數需寫入 `.env.example` 並更新其中文說明區塊
- `docker-compose.yml` 的 backend service 需在啟動指令前插入遷移腳本呼叫
- 回滾方案：`PRISMREEL_JWT_SECRET` 若移除環境變數，`enforce_login` middleware 對應也應設計為「未設定 JWT_SECRET 時完全停用登入閘門」（與現有 `PRISMREEL_API_KEY` 的「留空=不驗證」慣例一致），讓 desktop 單機模式 / 緊急回滾都不需要改程式碼，只需要調環境變數
