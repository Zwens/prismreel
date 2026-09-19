---
name: project_video_workflow_independent_audit_handoff_2026-09-18
description: 多鏡頭影片工作流(feature/video-workflow-multi-shot)獨立稽核進度交接——核心結論已定，僅剩瀏覽器E2E被本機環境問題卡住
metadata:
  type: project
---

## 🔴 本檔案是正式跨 session 交接內容，非「等原 session 回來繼續」
2026-09-18 稽核途中，使用者登出/重新登入 Windows 帳號釋放本機殭屍 process 狀態——這個動作會
**終止當時所有 Claude session**（含撰寫本檔案的 claude-wmzic-d9），不只是清進程。因此接手 Task 10
的必然是一個全新 session，不是原 session 回來續作。新 session 進來時，請先讀完本檔案全文
再動手，不要重新從頭排查已經在下面記錄過的環境坑。

## 背景
原 session（claude-wmzic-d9）擔任 `feature/video-workflow-multi-shot` 分支的**獨立稽核官**，
不採信開發方（claude-wmzic-f4，後由 claude-wmzic-15 接手協調）的裁定，自己重新查證。工作目錄：
`C:\Users\chenc\Documents\Claude Wmzic\prismreel-video-workflow-worktree`（獨立 git worktree），
HEAD 在 `374a7b9`（"fix(video-workflow): address final review findings"），尚未 merge 回 main。

## 已完成且結論確定的三項（不需重做）

### 1. Critical bug（model_id 空字串）修復 — ✅ 通過
獨立追蹤 `src/apps/playground/service.py` 實際路由邏輯：舊版 `model_id=''` 時
`model_lower.startswith(...)` 全部不 match，落到 `_generate_video_default` →
`resolve_ark_model_id('')` 回傳 `None` → `ValueError`，根因確認屬實。修復版改用
`getModelsForMode(mode)[0]?.id`，已用**真實 `frontend/src/generated/modelCatalog.json`**
資料驗證 t2v/i2v/r2v/v2v 四種模式的 `getModelsForMode()[0]` 都能拿到非空真實模型 id
（皆落在 `seedance-2.5-*`，已存在於 `src/models/byteplus.py` 的 `ARK_MODEL_IDS` 對照表）。
v2v 目前只有一個 `status:hidden` 模型可用、無 fallback，屬已知營運注意事項非 bug。

### 2. 排序 UI 範圍收斂 — ✅ 通過
Grep 確認 `insertShotHere` 只殘留在三個 i18n 訊息檔案（en/zh/zh-Hant.json），
`ShotCard.tsx`/`VideoWorkflowPage.tsx` 完全沒有引用該 key，只有 `moveShot` 綁定的
上/下移動按鈕（`onMoveUp`/`onMoveDown`）。符合使用者中途確認的範圍收斂決策。

### 3. 自動化測試 — ✅ 全綠
獨立重跑前端 37 個相關測試：`npm run test:ui -- videoworkflow shot`（component，12個）+
`npm test -- shot`（node-env，25個）全數通過。含一個涵蓋 generate→combine 完整流程的
真實整合測試（`VideoWorkflowPage.spec.tsx` 第99行起，只 mock `playgroundApi` 網路邊界，
非拆解成獨立單元各自 mock），驗證 combine 呼叫時 outputPath 順序正確。

## 唯一未完成：Task 10 手動瀏覽器 E2E（原本 f4 就沒做過的部分）

**卡住原因**：本機開發環境的「環境配置」彈窗必填 Gemini API Key 才能進入應用。這個坑
**已有舊記憶記錄** [[feedback_env_config_dialog_writes_global_env_not_per_account_2026-09-18]]：
`POST /config/env` 寫入的是**專案根目錄全域 `.env`**，不是 per-worktree/per-account 隔離。
本次重演見 [[feedback_env_config_global_env_gotcha_recurred_worktree_2026-09-18]]——誤判為
worktree 間 process/port 衝突，花了 30+ 分鐘排查 `netstat`/`Get-NetTCPConnection`，過程中
一度 kill 了主 repo 的殘留 backend process（PID 688/31032，事後才確認風險，使用者已知情同意）。

使用者最終決定嘗試「登出/重新登入 Windows 帳號」釋放殭屍 process/socket 狀態
（比照舊記憶第79行「多次嘗試清理無效時不必死磕，純本機開發用途可留待重開機釋放」的既有結論）。

## 接續步驟（登入/重開機後）
1. 確認 port 17177 無殘留 process：`Get-NetTCPConnection -LocalPort 17177 -State Listen`
2. Worktree 已有自己的 Python 3.12 venv（`prismreel-video-workflow-worktree/.venv`，
   因為預設 `.venv` 是 Python 3.14 缺 passlib）；後端啟動：
   `cd prismreel-video-workflow-worktree && node scripts/start-backend.js`
3. 前端啟動（**port 3008 可能被其他 session 佔用**，改用 3108）：
   `cd frontend && PORT=3108 npm run dev`
4. `.env`（全域共用檔）已經有使用者提供的真實 Gemini API Key，理論上瀏覽器開啟時
   環境配置彈窗應該不會再跳出；若還是跳出，直接透過瀏覽器 UI 手動填入即可，
   不要用 fetch/curl 硬灌，減少誤觸全域檔案的風險
5. Task 10 步驟：建立 2 個混合媒體鏡頭（一個純文字 t2v、一個雙圖 r2v）→
   Generate all → 等待都 completed → Combine into final video → 播放驗證
   shot 1 內容在 shot 2 之前（順序正確性是 spec 的核心保證）
6. 截圖存到 workspace `screenshot/` 目錄（CLAUDE.md 鐵律，不落地工作區根目錄）

## 未決定事項（需再次請示使用者）
使用者一度提出「掛版本號、部署到VPS live環境驗證」取代 localhost E2E，但後來選擇
先解決 localhost 問題。若接續 session 決定改走部署路線，注意：
- 這是**未合併的 feature branch**，部署前需先與使用者確認是否要先 merge 回 main
- Merge/部署操作屬於 CLAUDE.md §1「不可逆/影響共享系統」動作，需使用者明確授權才能執行
- Peer session claude-wmzic-15 已提醒：merge/部署決定不能由對方 session 的使用者代為授權，
  只有本 session 的使用者直接指示才算數

## 相關
[[feedback_env_config_dialog_writes_global_env_not_per_account_2026-09-18]] — 環境配置全域寫入原始事故
[[feedback_env_config_global_env_gotcha_recurred_worktree_2026-09-18]] — 本次重演記錄
