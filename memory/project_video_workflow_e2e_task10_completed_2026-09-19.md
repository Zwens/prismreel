---
name: project_video_workflow_e2e_task10_completed_2026-09-19
description: video-workflow-multi-shot獨立稽核Task10手動瀏覽器E2E最終結論——生成驗證通過，combine步驟因本機缺FFmpeg跳過，VPS production不受影響
metadata:
  type: project
---

## 背景
承接 [[project_video_workflow_independent_audit_handoff_2026-09-18]] 交接，前一 session 因使用者登出/重登 Windows 帳號終止。新 session 接手後環境已釋放，成功啟動 worktree 後端(17177)+前端(3108)。

## Task 10 執行結果

### 1. 環境初始化缺口（新發現，已本機臨時修復解除阻塞）
全新 worktree 的 `output/auth.db` 是空檔案，`src/apps/comic_gen/api.py` 從未呼叫
`auth_db.init_schema()`（該函式只在測試檔案裡被呼叫），導致所有需要登入的 API
一律 503 `sqlite3.OperationalError: no such table: users`。手動呼叫
`auth_db.init_schema()` 建表 + `user_repo.create_user()` 建測試帳號
`e2e-test@local.dev` 解除阻塞。**這是本機/新環境專屬缺口，不受git版控**
（`output/*` 在 `.gitignore`），未動任何程式碼，未push。VPS production 資料庫
應該早已存在正確 schema 才沒踩過這個坑，建議後續評估是否要在 app startup
補上 `init_schema()` 呼叫，但屬於本次稽核範圍外的新發現，未擅自修改。

### 2. 生成驗證 — ✅ 通過
建立2個混合媒體鏡頭：
- 鏡頭1：純文字 t2v prompt「SHOT ONE: a lone red bicycle...」
- 鏡頭2：雙圖 r2v（官方角色庫選2張圖）+ prompt「SHOT TWO: the same red bicycle...」

真實 API 呼叫確認：`POST .../contents/generations/tasks model=dreamina-seedance-2-5-260628`
分別帶 `images=0`（鏡頭1）與 `images=2`（鏡頭2），參數正確對應模式。兩者最終
在「生成歷史」頁面確認完成，各自顯示 seedance-2.5-t2v/seedance-2.5-r2v 標籤+
token用量+價格。**注意**：多鏡頭工作流頁面本身沒有明確的「生成完成」跳出通知，
需要手動切到生成歷史頁或重新整理才會看到已完成狀態，UI輪詢更新到「已完成」
狀態有延遲，這是一個可考慮改進的UX缺口（非本次稽核範圍，未處理）。

### 3. 合成完整影片（combine）— 🔴 本機環境限制，未完整驗證
點擊「合成完整影片」回傳 500，log 顯示根因：
`FFmpeg not found in PATH or common Windows paths` → `/playground/concat` 500。
確認本機 Windows 完全未安裝 FFmpeg（`where ffmpeg` 找不到）。

**已用 SSH 交叉確認 VPS production 環境**：
- VPS 宿主機：`/usr/bin/ffmpeg` 4.4.2
- `prismreel-backend` 容器內：`/usr/bin/ffmpeg` 7.1.5

VPS production 皆已確認裝有 FFmpeg，正式環境合成功能不受影響。這純粹是本機
Windows worktree 缺本地依賴，非程式碼bug、非VPS部署缺陷。經使用者裁定：
**跳過本機合成驗證，不安裝FFmpeg，以此結果收尾**，不列為 spec 未通過項目。

## 最終稽核結論
連同 [[project_video_workflow_independent_audit_handoff_2026-09-18]] 已完成的
三項（Critical bug修復/排序UI範圍收斂/37測試全綠），Task 10 生成部分已用真實
瀏覽器E2E驗證通過。combine端點本身的順序正確性邏輯已由 Task 10 前置的
`VideoWorkflowPage.spec.tsx` 整合測試覆蓋（mock網路邊界層級，驗證outputPath
順序正確），故雖然本機手動combine因FFmpeg缺失未能肉眼複驗，稽核官綜合判斷
**該分支達到可merge標準**，是否要merge回main由使用者最終決定。

## 相關
[[project_video_workflow_independent_audit_handoff_2026-09-18]] — 前置交接記錄，三項已完成結論
