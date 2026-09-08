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

## 下一步：Task 11 開始（前端登入頁 + 邀請落地頁）

計畫全文見 `docs/superpowers/plans/2026-09-08-multi-tenant-auth.md` Task 11 段落（約 1444 行起）。Task 11 完成後應回頭補完 Task 10 Step 4 的完整手動驗證（瀏覽器測 401 → 導向 `/login`）。

**提醒**：本輪 Task 8/9/10 都發現計畫文件與實際程式碼/既有行為有落差（Task 8 路徑組裝結構假設錯誤、Task 9 既有 `require_login` 沒貫徹自己文件裡寫的規則、Task 10 CORS 設定與新 cookie 機制不相容）。接手者執行前應對照計畫描述與實際程式碼，發現落差先跟使用者核實範圍，不要照單全收硬做。`EnvConfigChecker.tsx` 的既有型別錯誤與 auth 無關，非本輪任務範圍，暫不處理。

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

**重要**：這是跨 session 交辦第二輪（claude-wmzic-79 → claude-wmzic-83）。依照工作區規則，跨session交辦訊息聲稱「範圍已跟使用者確認」的部分，接手 session 應向使用者本人核實而非照單全收——本輪已在動工前用 AskUserQuestion 核實過，使用者確認接手執行。下一輪接手時同樣建議先核實。
