---
name: project-auth-implementation-handoff-2026-09-08
description: 多租戶登入系統實作進度交接——Task 1-5已完成並commit，下一個session從Task 6接手
metadata:
  type: project
---

## 現況（2026-09-08）

**分支**：`feature/multi-tenant-auth`（從 `main` 切出，工作目錄乾淨）
**計畫文件**：`docs/superpowers/plans/2026-09-08-multi-tenant-auth.md`（14 個 Task，全文含每步驟的程式碼與驗證指令，接手前務必通讀）
**設計 spec**：`docs/superpowers/specs/2026-09-08-multi-tenant-auth-design.md`（已經使用者審閱確認，8 項架構決策不要重新問）

## 已完成（Task 1-5，共 8 個 commit）

1. `feat(auth): add password hashing and JWT token core module` — `src/apps/comic_gen/auth.py`/`auth_db.py`
2. `feat(auth): add user repository and FastAPI auth dependencies` — `src/apps/comic_gen/user_repo.py`
3. `fix(auth): reject weak PRISMREEL_JWT_SECRET at startup` — 計畫外修正，見下方「偏離計畫之處」
4. `feat(auth): add /auth/* and /admin/* endpoints` — `api.py` 新增登入/邀請/admin 端點，**同時提前實作了原本排在 Task 5 的 `get_owned_script`/`get_owned_series` dependency**（因為邏輯上同屬一個 auth 區塊）
5. `feat(auth): add idempotent auth migration script` — `scripts/migrate_auth_v1.py`
6. `feat(auth): add owner_id fields to Script and Series models` — `models.py`

全部 24 個既有+新增測試通過（`pytest src/apps/comic_gen/ --deselect src/apps/comic_gen/test_pipeline.py::test_pipeline`；`test_pipeline` 需要真實 LLM API Key，這個環境沒配，跟本次改動無關，不用管）。

## 偏離計畫之處（重要，接手前要知道，不要重新做決策）

1. **`get_owned_script`/`get_owned_series` 提前到 Task 3 就實作**（計畫寫在 Task 5）。原因：這兩個 dependency 邏輯上跟 `/auth/*` `/admin/*` 端點同屬一個 auth 區塊，放一起改比較不零碎。Task 5 執行時我只做了「加 `owner_id` 欄位 + 補測試」，dependency 本身已經在 api.py 裡了，不要重複寫。
2. **bcrypt 版本相容性問題**（計畫沒預料到）：`passlib 1.7.4`（已停止維護的最後一版）透過 `bcrypt.__about__.__version__` 探測版本，但 `bcrypt>=4.1` 拿掉了這個屬性，導致 passlib 內部誤判成「密碼超過 72 bytes」的假錯誤，即使密碼很短也一樣炸。已在 `requirements.txt`/`requirements-docker.txt` 釘選 `bcrypt==4.0.1` 解決，本機環境也已重裝成這個版本。**Docker build 環境要注意這個釘選有沒有生效**（Task 13 會重新 build，屆時留意）。
3. **安全掃描建議追加的弱密鑰拒絕檢查**：`auth.py` 裡 `JWT_SECRET` 非空但 < 32 字元時，模組載入直接 `raise RuntimeError`。這不是計畫原文，是自動化安全掃描發現「留空=停用」的設計沒有下限檢查後，經使用者確認採納的追加修正。**留空仍然=停用（這是刻意設計，不要改掉）**，只有「非空但太短」才拒絕。這也導致 `test_auth.py`/`test_user_repo.py` 裡的測試用密鑰從原計畫的短字串改成 32+ 字元（`test-secret-for-unit-tests-32chars-min`、`test-secret-needs-32-chars-minimum`），若你之後新增測試也要用 32+ 字元的密鑰，不然會被這個檢查擋下來炸測試。
4. **本機 Python 環境細節**：這台機器 `python`/`python3` 指令預設指向 `C:\Users\chenc\AppData\Local\Python\bin\python.exe`（3.14，沒裝專案依賴），實際要用的是 `C:\Users\chenc\AppData\Local\Programs\Python\Python312\python.exe`（3.12，已裝好 fastapi/pytest/passlib/bcrypt==4.0.1/dashscope 等全部依賴）。跑任何 `pytest`/`uvicorn` 指令都要用完整路徑指到 Python312，否則會報 `ModuleNotFoundError`。
5. **`requirements-dev.txt` 檔案本身是正常 UTF-8**，但 `pip install -r requirements-dev.txt` 在這台機器的系統 codepage（GBK/cp936）下會讀取失敗報 `UnicodeDecodeError`。這是既有環境問題非本次改動造成，繞過方式是直接 `pip install pytest httpx` 等單獨裝，不要浪費時間排查這個 codepage 問題。

## 下一步：從 Task 6 開始接手

計畫檔案 `docs/superpowers/plans/2026-09-08-multi-tenant-auth.md` 裡 Task 6 開頭寫著「找到 `create_project` 函式內建立 `Script(...)` 的呼叫方式，先 Read 確認再改」——這幾處計畫故意留白要求執行時查證，不是缺內容，照著做即可。

**Task 6-7 是整個計畫工作量最大的部分**：api.py 有 60+ 個 `{script_id}`/`{series_id}` 端點都要加 owner 過濾，改法是把函式簽名裡的 `script_id: str` 改成 `script: Script = Depends(get_owned_script)`，取代現有手寫的 `pipeline.get_script(script_id)` + 404 判斷樣板。**這個規模已經跟使用者確認過要一次到位全部做**（不是分階段），不要重新問使用者要不要縮小範圍。

**Task 8 的 `/files/` 路徑隔離也已經跟使用者確認策略**：舊全域路徑（`output/assets` 等）維持現狀不做強制驗證，只有新路徑 `output/users/{owner_id}/...` 用自訂 middleware 強制驗證。這是因為 `StaticFiles` mount 機制沒有 per-request hook 點可以塞 owner 判斷，此落差已記錄在計畫的「與 spec 的已知落差」段落，不要重新猶豫要不要改全域路徑。

## 部署相關提醒（跟登入系統改動疊加）

- git push 不會自動部署到 `prismreel.soulo-ai.com`，VPS（`vps_main`/202.182.117.182，`/opt/prismreel`）是手動 scp + docker rebuild，見 [[feedback_git_push_does_not_deploy_manual_vps_sync_required]]
- 這次會新增環境變數 `PRISMREEL_JWT_SECRET`（≥32字元）/`PRISMREEL_ADMIN_EMAIL`/`PRISMREEL_ADMIN_PASSWORD`，上線前要手動加進 VPS 的 `.env`，細節見計畫 Task 13-14
- **在 Task 13 Docker build 驗證階段，務必確認 `bcrypt==4.0.1` 有正確安裝進容器**（見上方偏離計畫之處 #2），這是本機開發環境才發現的坑，Docker build 用的是全新環境，理論上 requirements.txt 釘選版本會自動生效，但務必實際驗證不要假設。

## 執行方式

使用者選擇 **Inline Execution**（本 session 內批次執行，非 subagent-driven），呼叫 `superpowers:executing-plans` skill 執行。接手後延續同樣模式，在 `feature/multi-tenant-auth` 分支上繼續，每個 Task 完成後照計畫要求的驗證步驟做完才 commit。
