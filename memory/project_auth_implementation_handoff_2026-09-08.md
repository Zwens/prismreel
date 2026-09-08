---
name: project-auth-implementation-handoff-2026-09-08
description: 多租戶登入系統實作進度交接——Task 1-7已完成並commit，下一個session從Task 8開始
metadata:
  type: project
---

## 現況（2026-09-08，claude-wmzic-83 更新）

**分支**：`feature/multi-tenant-auth`（從 `main` 切出，工作目錄乾淨）
**計畫文件**：`docs/superpowers/plans/2026-09-08-multi-tenant-auth.md`（14 個 Task，全文含每步驟的程式碼與驗證指令，接手前務必通讀）
**設計 spec**：`docs/superpowers/specs/2026-09-08-multi-tenant-auth-design.md`（已經使用者審閱確認，8 項架構決策不要重新問）

## 已完成（Task 1-7，共 10 個 commit）

Task 1-5（claude-wmzic-79 完成，見 git log）：auth 核心模組、user repository、`/auth/*`+`/admin/*` 端點、遷移腳本、`owner_id` 欄位 + `get_owned_script`/`get_owned_series` dependency。

Task 6（本輪 commit `f42a1e3`）：`POST/GET/DELETE /projects/{script_id}`、`GET /projects/` 套用 owner 過濾，手動驗證兩帳號互相看不到對方專案（curl 實測 404/200 皆正確）。

Task 7（本輪 commit `45e7a48`）：**全部約 100 個** `/projects/{script_id}/*`、`/series/{series_id}/*` 端點改用 `Depends(get_owned_script)`/`Depends(get_owned_series)`，取代手寫 `pipeline.get_script(script_id)` + 404 樣板。逐端點手動改寫（非批次字串替換），因為很多端點簽名細節不同（有的直接查 script 物件用屬性、有的把 `script_id` 字串傳給底層 pipeline 函式）。

**Task 7 過程中發現並修正兩個計畫原文未列出的缺口**（不在原始 Task 6/7 清單裡，但邏輯上必須做，否則隔離會漏洞）：
1. `POST /series`、`POST /series/import/confirm` 建立新 Series/Script 時原本沒寫入 `owner_id`——`pipeline.create_series`/`create_series_from_import` 補了 `owner_id` 參數
2. `/library/assets/*`（全域資產庫，spec 明確規定不做 owner 過濾）原本連登入都不要求——補上 `Depends(auth.require_login)`（不做 owner 過濾，符合 spec）

驗證：語法檢查通過、server 啟動無路由註冊錯誤、寫了一支 AST 掃描腳本確認**零殘留**未套用 dependency 的 `{script_id}`/`{series_id}` 端點、`pytest` 全數通過（含 pipeline/shared_asset_pool/auth 全套測試），一支既有 TestClient 測試因為新閘門生效改成 401 而需要 monkeypatch 假登入使用者才能繼續測原本要測的東西（非迴歸，是預期行為）。

## Task 8 已完成（claude-wmzic-26 本輪，commit `915dde3`）

**與計畫的落差**：計畫 Step 1 假設有單一「新專案輸出路徑組裝函式」可改，實測 grep 後發現不存在——`pipeline.py` 裡輸出路徑分散在 40+ 處各自呼叫 `_safe_resolve_path("output", ...)`（圖片生成/影片合成/音訊/字幕等）。已用 AskUserQuestion 跟使用者核實範圍，使用者確認縮小為：只改「真正新建立輸出檔案」的關鍵點，讀取既有 URL 的路徑解析邏輯不動。

**實作**：
1. `api.py` 加 `app.mount("/files/users", ...)` + `enforce_file_ownership` middleware（依計畫原文）——middleware 是 ASGI 層外層攔截，比對 `request.url.path`，與 StaticFiles mount 註冊順序無關（403 直接短路，不進 mount 路由）
2. `pipeline.py` 新增 `_project_output_dir(script, *subdirs)` helper：`owner_id` 為空（舊資料）走原本 `output/...`，非空則走 `output/users/{owner_id}/{script_id}/...`
3. 改了 4 個關鍵新建檔案點：影片合成輸出、影片預覽輸出、背景音 Demucs 快取（讀寫兩處都要改，因為 `frame.bg_audio_url` 只存相對路徑片段、讀取時重新組裝，不是走 `to_project_media_ref` 那種「相對於 output 根」的通用參考格式）、字幕匯出、抽幀截圖（`extract_last_frame`，這個不需要動讀取端，因為它走 `to_project_media_ref` 產生的相對路徑，既有 `_safe_resolve_path("output", url)` 讀取邏輯本來就相容更深子路徑）

**驗證**：新測試 `test_file_ownership_middleware.py` 4/4 過；`pytest src/apps/comic_gen/` 28/29 過（`test_pipeline` 失敗是既有環境缺 LLM API Key，用 git stash 驗證改動前也一樣失敗，非迴歸）；`ast.parse` 語法檢查過；app import 啟動無路由註冊錯誤。

## Task 9 已完成（claude-wmzic-26 本輪，commit `a00b2b3`）

依計畫實作 `enforce_login` middleware，但發現並修正一個既有 bug：`require_login`（Task 2 寫的 dependency，`GET /projects/` 等端點在用）沒有遵守 `auth.py` 檔頭註解明載的「`JWT_SECRET` 留空 = 完全停用登入閘門」規則，一律要求已登入。已跟使用者確認後修正：`require_login` 在 `JWT_SECRET` 未設定時回傳 `_ANONYMOUS_ADMIN`（role="admin"，讓既有 `user.role != "admin"` 過濾邏輯自然給予完整存取），與新 middleware 行為一致。

計畫測試程式碼本身也有兩個小缺口，接手時已修正：範例 JWT secret 只有 11 字元（低於 auth.py 強制的 32 字元下限）、`test_auth_login_endpoint_accessible_without_cookie` 缺少其他 auth 測試都在用的 `isolated_db` fixture（否則打到真實 `output/auth.db` 沒有 `users` 表）。

**驗證**：新測試 4/4 過；`pytest src/apps/comic_gen/` 32/33 過（`test_pipeline` 同樣是既有環境缺 LLM API Key，非迴歸）；語法檢查+app 啟動皆過。

## Task 10 已完成（claude-wmzic-26 本輪，commit `7b42f0e`）

依計畫加 `axios.defaults.withCredentials = true` + `authInterceptor.ts`（401 導向 `/login`），安裝點放在 `Providers.tsx`（根 `layout.tsx` 是 server component，`Providers` 才是最外層 client component，符合計畫 Step 3 的判斷邏輯）。

**額外發現並修正的落差**：`withCredentials=true` 要求後端 CORS 回應明確 origin（不能是 `"*"`），但既有 `enforce_api_key`/CORS 設定只在 `PRISMREEL_CORS_ORIGINS` 明確設定時才開 `allow_credentials`——dev 模式（前端 `localhost:3008`、後端不同 port，跨 origin）預設會讓登入 cookie 送不出去，登入系統實質失效。已跟使用者確認後修正：`PRISMREEL_CORS_ORIGINS` 未設定時，改用 `allow_origin_regex` 只放行 `localhost`/`127.0.0.1`（任意 port），生產環境設定了該環境變數則維持原本明確 allowlist 行為不變。

**未完成/略過**：Step 4 手動驗證只做到「dev server 啟動無錯誤」，計畫本文也註明「完整驗證需等 Task 11 登入頁存在」，尚未實際打開瀏覽器測 401 導向（因為 `/login` 頁面還不存在，Task 11 才建立）。

**驗證**：新檔案 `authInterceptor.ts` 獨立 tsc 檢查過；`npm run typecheck` 有 1 個既有型別錯誤（`EnvConfigChecker.tsx`，用 git stash 驗證改動前就存在，非本次引入，不在 Task 10 範圍內未處理）；後端 `pytest` 32/33 過（同樣既知的 `test_pipeline` LLM Key 缺失，非迴歸）；Next.js dev server 手動啟動確認無錯誤。

## Task 11 已完成（本 session，commit `8075003`），但發現一個未修的關鍵架構 bug——下一輪必須先處理

**實作**：`api.ts` 加 `login`/`redeemInvite`/`logout`/`getCurrentUser`；`frontend/src/app/login/page.tsx`（Atelier 視覺風格，`bg-background` 取代計畫範例寫錯名的 `var(--color-bg,...)`）；`frontend/src/app/redeem/page.tsx`（改用 `?code=xxx` query string，非計畫原文的 `/redeem/[code]` 動態路由——後者在 `output: export` 生產 build 下因 `generateStaticParams()` 缺失會直接編譯失敗，邀請碼又不可能 build time 窮舉，已用 AskUserQuestion 核實後改掉）。

**本輪同時修的三個真實 bug**（皆非本次引入，是 Task 8/9/10 留下、遇到才發現，每個都先 AskUserQuestion 核實過才動手）：
1. `set_cookie` 硬編碼 `secure=True`，dev 模式 http localhost 下瀏覽器不存 cookie，登入形同虛設。改用 `_cookie_secure = bool(_cors_origins_env)`，跟 Task 10 CORS 用同一個 dev/prod 判斷訊號。
2. `auth.py` 模組層級建立 `_ANONYMOUS_ADMIN = user_repo.User(...)`，但 `user_repo.py` 頂層先 `from .auth import ...`（在 `User` class 定義之前）——任何先 import `user_repo` 的入口點（如 `scripts/migrate_auth_v1.py`）都會循環引入崩潰。改成 `_get_anonymous_admin()` lazy singleton。
3. `EnvConfigChecker` 掛在根 layout 對所有路由渲染，登入閘門生效後未登入狀態呼叫 `getEnvConfig()` 必 401，被 catch 分支誤判成「環境未配置」彈窗蓋住登入表單。改成 `/login`、`/redeem` 路徑不渲染該元件。

**🔴🔴 發現但依使用者指示暫不修、必須列入下輪第一件事處理**：`enforce_login` middleware（`api.py:127`）在 401 短路時 `return JSONResponse(...)`，但它是在 `CORSMiddleware`（`api.py:99`）**之後**用 `@app.middleware("http")` 註冊的。Starlette middleware 執行順序是反向的（後註冊的先執行），所以這個 401 回應完全繞過 `CORSMiddleware`，瀏覽器收到沒有 `access-control-allow-origin` 標頭的回應會直接擋掉整個 response——JS 端只看到 axios `Network Error`，`error.response` 是 `undefined`，**Task 10 的 401 導向攔截器（`authInterceptor.ts`）因此完全無法觸發**。已用 curl 帶 `Origin` header 實測驗證（`/health` 200 回應有 CORS 標頭，`/config/env` 401 回應沒有）。這不只是手動驗收問題——正式上線後任何使用者 session 過期都會卡在「項目同步失敗 Network Error」畫面，不會被導向登入頁。**下一輪接手第一件事**：把 `CORSMiddleware` 改成在所有 `@app.middleware("http")` 函式**之後**才 `add_middleware`，確保它在最外層能處理所有短路回應，改完要用 curl 帶 Origin header 重新驗證 401 回應是否帶 CORS 標頭，再用瀏覽器實測登出後重新整理是否正確導向 `/login`（本輪就是卡在這步發現的）。

**驗證**：後端 `pytest src/apps/comic_gen/` 32/33 過（`test_pipeline` 同樣既知的 LLM Key 缺失，非迴歸）；前端 `npm run typecheck` 生產 build 通過、`/login`+`/redeem` 正確靜態匯出，唯一殘留錯誤是既有的 `EnvConfigChecker.tsx` 型別問題（非 auth 相關，非本輪範圍）；瀏覽器 Playwright 實測登入頁視覺（暖深底+玻璃面板+Fraunces 標題字皆正確）、實際輸入帳密登入成功導向首頁 cookie 正確存住；**登出後 401 導向測試失敗**（上述 CORS bug），這就是發現該 bug 的過程。

## CORS+401 middleware 順序 bug 已修復（本輪，commit `18b0c72`，第五輪交接）

**根因確認**：Starlette middleware stack 執行順序是「後註冊者在外層」。`app.add_middleware(CORSMiddleware, ...)` 原本寫在 `api.py:99`，早於所有 `@app.middleware("http")` 裝飾器（`enforce_api_key`/`enforce_login`/`rate_limit_generation_endpoints`/`add_cache_control_header`/`enforce_file_ownership`），導致 CORSMiddleware 其實被疊在最內層——任何後面註冊的 middleware 短路回應（401/403/429）都不會經過它。

**修法**：把 `app.add_middleware(CORSMiddleware, ...)` 呼叫本身移到所有 `@app.middleware("http")` 函式定義**之後**（`enforce_file_ownership` 定義結束後），配置值計算（`_cors_allow_origins`/`_cors_allow_credentials`/`_cors_allow_origin_regex`/`_cookie_secure`）留在原位不動，只搬呼叫本身。

**驗證**：
1. 重建本機 `.env`（`PRISMREEL_JWT_SECRET`/`PRISMREEL_ADMIN_EMAIL`/`PRISMREEL_ADMIN_PASSWORD`）+ 重跑 `scripts/migrate_auth_v1.py` 成功
2. `ast.parse` 語法檢查過；uvicorn 啟動無路由註冊錯誤
3. **curl 帶 `Origin: http://localhost:3008` header 重新驗證**：`/health`（200）與 `/config/env` 未帶 cookie（401）**現在都回傳** `access-control-allow-origin: http://localhost:3008` + `access-control-allow-credentials: true` —— 修復前 401 回應是沒有這兩個標頭的，這正是交接文件記錄的 bug 現象
4. `pytest src/apps/comic_gen/` 32/33 過（`test_pipeline` 同樣既知的 LLM Key 缺失，非迴歸）

**未完成**：瀏覽器端到端驗證（登出後重整是否導向 `/login`）本輪**卡在 Chrome 擴充功能本身**——`mcp__claude-in-chrome__computer`/`read_page`/`get_page_text` 對 `localhost:3008/login` 全部回報 `Frame with ID 0 is showing error page`，重開分頁、改用 `127.0.0.1` 皆同樣結果，但 `curl` 直接打前端 3008 和後端 17177 都正常回應，判斷是瀏覽器自動化工具連線問題而非應用程式問題。已用 AskUserQuestion 跟使用者核實，使用者選擇「先跳過瀏覽器驗證，直接 commit CORS 修復」。**下一輪如果要補做這步**：先確認 Chrome 擴充功能本身是否正常連線（`mcp__claude-in-chrome__tabs_context_mcp` 能列出 tab 但截圖/讀頁失敗，可能是分頁層級的暫時性問題），或考慮改用 Playwright MCP 工具重試。

**本機測試環境**：本輪建立的測試用 `.env` 與 migration marker（`output/.auth_migrated`）**未清除**，留給下一輪直接可用，內容為：`PRISMREEL_JWT_SECRET=test_local_dev_jwt_secret_key_32chars_minimum_ok`、`PRISMREEL_ADMIN_EMAIL=admin@test.local`、`PRISMREEL_ADMIN_PASSWORD=TestAdminPass123`。

## 瀏覽器端到端驗證已補做（本輪，透過 Task 12 實作過程），CORS bug 徹底確認修復

上一輪記錄的 Chrome 擴充功能連線問題（`mcp__claude-in-chrome__*` 全部回報 `Frame with ID 0 is showing error page`）本輪改用 **Playwright MCP**（`mcp__plugin_playwright_playwright__*`）繞過，運作正常。完整跑了一次登入→登出→訪問受保護路由的流程：
- admin 登入 `http://localhost:3008/login` 成功導向 `/`，側欄正確顯示新增的「登出」按鈕
- 點擊登出按鈕：頁面導向 `/login`（`logout()` API 呼叫成功）
- 登出後直接導覽到 `/admin/users`（受 `enforce_login` 保護）：**正確 401 並被攔截器導向 `/login`** —— 這正是上一輪 CORS middleware 順序 bug 修復前完全無法觸發的行為，現在完整驗證通過

## Task 12 已完成（本輪，commit `a6daa30`）

**與計畫的落差**（動工前已用 AskUserQuestion 逐一跟使用者核實）：
1. 計畫假設側欄有獨立「齒輪圖示按鈕」可在上方插入登出圖示——實際 `GlobalSidebar.tsx` 的 Settings 是帶文字標籤的 `NavButton`（icon+label），沒有純圖示按鈕，整個側欄也沒有目前登入使用者的角色資訊。確認後改為：在 Settings `NavButton` 下方新增一個同樣視覺風格的登出 `NavButton`（`lucide-react` 的 `LogOut` icon + i18n `nav.logout` 文字），不判斷 admin 角色、所有已登入使用者皆可見。三語系（`en`/`zh`/`zh-Hant`）messages 都補了 `nav.logout` key。
2. 計畫 admin 頁面程式碼範例產生的邀請連結是 `/redeem/{invite_code}`（動態路由），但 Task 11 已把 `/redeem` 改成 `?code=xxx` query string 路由（因為 `output: export` 靜態匯出下動態路由段需要 `generateStaticParams()`，邀請碼不可能 build time 窮舉）。`admin/users/page.tsx` 建立邀請連結時已改用 `${origin}/redeem?code=${invite_code}`。
3. 計畫未提及側欄要有「前往 Admin 後台」的入口——確認後維持計畫原始範圍，不加入口，admin 使用者直接輸入網址 `/admin/users` 訪問即可（頁面內部用 `getCurrentUser().role` 判斷，非 admin 會被 `router.push("/")` 導回首頁）。
4. `admin/users/page.tsx` 內部原本計畫程式碼有 `.catch(() => router.push("/login"))`，會跟全域 `authInterceptor.ts` 的 401 攔截器（`window.location.href = "/login"`）重複觸發跳轉、互相競爭——實作時已移除該 catch 分支，統一交給全域攔截器處理（跟 `login`/`redeem` 頁面的既有模式一致）。

**未偏離之處**：後端 `/admin/users`、`/admin/invites`、`/admin/users/{id}/reset_password`、`/admin/users/{id}/deactivate` 四個端點簽名與計畫描述完全一致，`api.ts` 新增的四個 admin 函式與 `admin/users/page.tsx` 的資料串接邏輯基本照計畫範例（僅上述 4 點修正）。

**驗證**：
- `npm run typecheck`：唯一殘留錯誤是既有的 `EnvConfigChecker.tsx`（已用 `git stash` 確認改動前就存在，非本輪引入，非 auth 相關）
- `npm run lint`：唯一命中本輪修改檔案的是 `frontend/src/lib/api.ts:108` 的 `_removed` 未使用變數警告，經 `git diff` 確認不在本輪 diff 範圍內，是既有問題
- `npm run test`（vitest）：194/194 全過，含 `i18n.test.ts`（驗證三語系 key 對齊，新增的 `nav.logout` 沒有破壞既有完整性檢查）
- `pytest src/apps/comic_gen/`：32/33 過（`test_pipeline` 既知 LLM Key 缺失，非迴歸）
- **Playwright 端到端瀏覽器測試**（見上方段落）：admin 登入 → `/admin/users` 列出使用者清單 → 建立邀請連結（格式驗證為 `/redeem?code=xxx`）→ 開啟連結完成註冊自動登入 → 新 member 帳號訪問 `/admin/users` 被導回 `/` → 側欄登出按鈕點擊後導向 `/login` → 登出後訪問受保護路由觸發 401 並被攔截器導向 `/login`，全部通過

**測試中額外發現的環境細節（非程式碼 bug）**：本機 `output/auth.db` 裡既有的 `admin@test.local` 帳號密碼跟本輪 `.env` 的 `PRISMREEL_ADMIN_PASSWORD` 不一致（因為 migration marker `output/.auth_migrated` 已存在，`migrate_auth_v1.py` 不會重新建立/更新既有 admin 密碼）。用 `user_repo.set_password()` 手動重設密碼為 `.env` 內的值以利本輪測試，這只影響本機測試資料庫，非程式碼問題，下一輪如果密碼又對不上可用同樣方式處理或直接刪除 `output/auth.db` + marker 重跑 migration。

## 下一步：Task 13（部署設定）與 Task 14（VPS 上線）

計畫全文見 `docs/superpowers/plans/2026-09-08-multi-tenant-auth.md` Task 12 段落（約 1620 行起，Admin 後台+側欄登出按鈕）。**Task 10 Step 4 手動驗證仍未完整通過**——不是頁面不存在的問題（Task 11 已建），是上述 middleware 順序 bug 擋住的，修完 CORS 順序才能重跑這步驗證。

**提醒**：本輪 Task 11 又再度發現計畫與實際程式碼/既有行為有落差（`/redeem/[code]` 與 `output: export` 衝突、`secure=True` 與 dev http 衝突、`_ANONYMOUS_ADMIN` 循環引入、`EnvConfigChecker` 全域渲染衝突、CORS middleware 順序）。這是第四輪交接（79→83→26→本session），每一輪都至少踩到 2-3 個計畫與現實的落差，模式很清楚：**這份計畫文件的程式碼片段從未在本專案實際跑過**，接手者一律要先讀實際程式碼、AskUserQuestion 核實才動手，不要相信計畫範例程式碼能直接複製貼上。`EnvConfigChecker.tsx` 的既有型別錯誤（`Property 'trim' does not exist`）與 auth 無關，非本輪任務範圍，暫不處理。

## 偏離計畫之處（Task 1-5 遺留，仍適用）

見 git log 中 `c306408` commit 訊息與更早的交接內容摘要：
1. bcrypt 版本相容性：`bcrypt==4.0.1` 已釘選（`requirements.txt`/`requirements-docker.txt`），**Task 13 Docker build 驗證階段務必再次確認**
2. `auth.py` 有弱密鑰拒絕檢查（`JWT_SECRET` 非空但 <32 字元時 `RuntimeError`）——留空仍=停用，這是刻意設計
3. 本機 Python 環境：一律用 `C:\Users\chenc\AppData\Local\Programs\Python\Python312\python.exe`（3.12，已裝好全部依賴含 bcrypt==4.0.1），不要用預設 `python`/`python3`（指向沒裝依賴的 3.14）
4. `requirements-dev.txt` 在這台機器 codepage 下 `pip install -r` 會 `UnicodeDecodeError`，繞過方式是單獨 `pip install pytest httpx` 等套件

## 部署相關提醒（跟登入系統改動疊加）

- git push 不會自動部署到 `prismreel.soulo-ai.com`，VPS（`vps_main`/202.182.117.182，`/opt/prismreel`）是手動 scp + docker rebuild
- 新環境變數 `PRISMREEL_JWT_SECRET`（≥32字元）/`PRISMREEL_ADMIN_EMAIL`/`PRISMREEL_ADMIN_PASSWORD`，上線前要手動加進 VPS 的 `.env`，細節見計畫 Task 13-14

## 執行方式

使用者選擇 **Inline Execution**（本 session 內批次執行，非 subagent-driven），用 `superpowers:executing-plans` skill 執行。接手後延續同樣模式，在 `feature/multi-tenant-auth` 分支上繼續，每個 Task 完成後照計畫要求的驗證步驟做完才 commit。

**重要**：這是跨 session 交辦第四輪（claude-wmzic-79 → claude-wmzic-83 → claude-wmzic-26 → 本session）。依照工作區規則，跨session交辦訊息聲稱「範圍已跟使用者確認」的部分，接手 session 應向使用者本人核實而非照單全收——本輪已在動工前用 AskUserQuestion 核實過，使用者確認接手執行；過程中又發現三個新落差（見上方 Task 11 段落），每個都個別核實過才動手。下一輪接手時同樣建議先核實，且務必先處理上方標記 🔴🔴 的 CORS+401 middleware 順序 bug，這是目前登入系統在瀏覽器裡唯一還無法端到端跑通的環節。

**本機測試環境提醒**：本輪測試用的 `.env`（含 `PRISMREEL_JWT_SECRET`/`PRISMREEL_ADMIN_EMAIL`/`PRISMREEL_ADMIN_PASSWORD`）與 `output/.auth_migrated` marker 已在收尾時清除，`.env` 本來就不受版控。下一輪要跑手動驗證需要重新建立本機 `.env` 並重跑 `scripts/migrate_auth_v1.py`（記得把變數 `set -a && source .env && set +a` 一起帶進 shell，腳本本身不會自動 `load_dotenv`）。
