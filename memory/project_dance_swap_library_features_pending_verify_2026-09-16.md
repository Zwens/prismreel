---
name: project_dance_swap_library_features_pending_verify_2026-09-16
description: 真人換裝舞蹈三項UI修復已push待CI build完成+live驗證，VPS系統負載過高(load 20.4)導致build異常緩慢
metadata:
  type: project
---

2026-09-16 使用者實測「真人換裝舞蹈」功能回報三個問題，已全部改完 push，**卡在最後一輪 CI build 遲遲未完成，尚未 live 驗證**。

**已完成並 push 的三個 commit（main 分支，依序）**：
1. `54c35a3` fix(library): resolve stored asset paths through mediaUrl before rendering — 素材庫破損圖片根因（`AssetLibraryPage.tsx`/`AssetInspector.tsx`/`AssetCard.tsx`/`ImportAssetsDialog.tsx` 四處顯示圖片時漏了 `mediaUrl()` 轉換，相對路徑直接塞進 `<img src>` 導致瀏覽器對錯 origin 解析成 404）
2. `57ba767` feat(dance): let users upload an existing character sheet, make it optional — Step1 三視圖改成二選一（AI生成/我已有三視圖上傳），Step3「使用三視圖」勾選框在無三視圖時自動 disable
3. `be41788` feat(dance): add pick-from-library option alongside upload in steps 1-2 — Step1/Step2 的「上傳」旁邊加「從素材庫選擇」按鈕，重用既有 `AssetSourcePicker` 元件（`frontend/src/components/modules/playground/AssetSourcePicker.tsx`）。**注意**：Step2（深度影片）的 picker `accept="video"` 時，`AssetSourcePicker` 內部邏輯只會顯示 `history` 來源（library/series/project/official 只存靜態圖，非既有 bug，是元件既定行為，見該檔案 176-186 行註解）

**當前卡點**：`be41788` push 後 CI `docker compose build frontend` 從 10:00 開始跑，截至使用者要求暫停時已跑 33+ 分鐘仍未完成（前兩次同類 build 分別約 15、22 分鐘），`docker images prismreel-frontend` 仍是舊版（09:54:52，ID `449234399a4a`），容器 `prismreel-frontend`/`prismreel-backend` 都還是 09:55 的舊版本在跑（**線上使用者目前看到的是 `57ba767` 那版，還沒有「從素材庫選擇」按鈕**）。

**已排查的根因**：非本次程式碼改動問題，非 build 卡死（`jest-worker` 子進程 CPU 持續有活動如 110%/17.8%，無 OOM kill 記錄）。真正原因是 **VPS(202.182.117.182) 系統負載過高**：`uptime` 顯示 `load average: 20.40, 8.23, 3.26`，同機同時跑著 `traffic-simulator`（proxy-gateway 兩支）、`playwright-core` 多個 channel（711p-pw-bduk/711p-pw/yy888/galaxy3-gofuntw 等 orchestrator，部分已累積數百小時 CPU time）、`n8n`、`gemini-api`、`ig-services` 等十幾個常駐服務，CI 的 docker build 只是在跟這些服務搶 CPU，排隊變慢。

**Why**：這是先前查證 Prismreel GEMINI_API_KEY/requirements-docker.txt 缺依賴問題（見 [[feedback_requirements_docker_missing_ai_ml_deps_2026-09-16]]）之後，使用者實測功能時連續回報的三個 UI 問題，逐一查證修復；卡在最後一步是基礎設施資源競爭，非程式邏輯問題。

**How to apply（新 session 接手時）**：
1. 先查 `docker ps --filter name=prismreel --format '{{.Names}}\t{{.Status}}\t{{.CreatedAt}}'` 確認容器是否已切到 `be41788` 之後的版本（`docker images prismreel-frontend` 的 `CreatedAt` 應該遠晚於 `2026-09-16 09:54:52`）。
2. 若已完成：做 §2 L3 驗收（等 60 秒快取生效 + `curl -s -o /dev/null -w "HTTP %{http_code}\n" https://prismreel.soulo-ai.com/` 3 次 + 通知使用者可以測 Step1/Step2「從素材庫選擇」按鈕、素材庫圖片顯示、Step1 三視圖可選）。
3. 若還沒完成：查 `ps aux | grep -iE 'next build'` 確認是否仍在推進（非卡死判準：子進程 `jest-worker` 有 CPU 活動、無 journalctl OOM 記錄），若使用者已在另一個 session 處理 VPS 負載，本 session 只需等待+驗證，不重複介入負載排查。
4. VPS 負載排查是**使用者本人在另開的 session 處理**，本 session 不越界處理該任務，避免兩個 session 同時動同一台 VPS 造成衝突（見 CLAUDE.md §2「操作起點三原則」第6條，動共用資源前應查 `_shared/session-status/`）。
