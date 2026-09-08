---
name: project-auth-handoff
description: 多租戶登入系統交接——spec已寫好待使用者審閱，下一個session從這裡接手實作
metadata:
  type: project
---

## 現況（2026-09-08）

**觸發原因**：使用者發現 https://prismreel.soulo-ai.com 完全沒有登入機制，後端裸奔（只有可選的 `PRISMREEL_API_KEY` 門禁，且 live 站台沒設定，已實測確認未開啟）。決定要做完整帳號登入系統。

**已完成**：
- 走完 superpowers:brainstorming 架構性路徑，跟使用者確認了全部關鍵決策
- 設計文件已寫好並 commit：`docs/superpowers/specs/2026-09-08-multi-tenant-auth-design.md`（commit `99e406e`）
- **spec 狀態：待使用者審閱，尚未進入 writing-plans / 實作階段**

## 已確認的架構決策（寫在 spec 裡，接手時直接照做，不要重新問使用者）

| 決策點 | 選擇 |
|---|---|
| 使用情境 | 多用戶 SaaS 化 |
| 隔離範圍 | 一次到位：登入 + 多租戶資料隔離（不分階段） |
| 註冊方式 | 邀請制／管理員建帳，不開放自助註冊 |
| Session 策略 | JWT + HttpOnly Cookie |
| 資料儲存 | 新增 SQLite（`output/auth.db`），不用外部服務 |
| 舊資料遷移 | 全部歸到一個新建的預設 admin 帳號 |
| 全域資產庫（library_assets.json） | **維持全域共享**，不隨 user_id 隔離（使用者明確要求，spec 裡記錄了這跟多租戶目標的張力） |
| 密碼重設 | 不做自助流程，管理員手動重設，不接 SMTP |
| 登入頁視覺 | 套用既有 Line B Atelier 設計語言 |

## 下一步（接手 session 該做的事）

1. **先問使用者**：spec 內容是否需要調整？確認沒問題後才繼續
2. 呼叫 `superpowers:writing-plans` skill，把 spec 轉成詳細實作計畫
3. 實作範圍涵蓋（spec 全文有細節）：
   - 後端新模組 `src/apps/comic_gen/auth.py`（bcrypt/JWT/FastAPI dependency）
   - SQLite schema（users/invites 表）+ 遷移腳本 `scripts/migrate_auth_v1.py`
   - 既有 `models.py` 的 Script/Series 加 `owner_id`
   - `pipeline.py` 讀寫不動，在 `api.py` 路由層做 owner_id 過濾（見 spec §3.3 的設計理由）
   - `output/` 檔案路徑隔離改成 `output/users/{owner_id}/{project_id}/...`
   - 前端：登入頁、admin 後台、邀請落地頁、axios cookie 設定、401 攔截導向

## 重要環境提醒（部署相關，實作完成要上線時必看）

這個專案 **git push 不會自動部署**，VPS（`vps_main`/202.182.117.182，`/opt/prismreel`）需要手動 scp 同步 + docker rebuild，詳見 [[feedback_git_push_does_not_deploy_manual_vps_sync_required]]。登入系統改動涉及後端（`docker compose build backend`）+ 前端都要重建，且這次會新增環境變數（`PRISMREEL_JWT_SECRET`/`PRISMREEL_ADMIN_EMAIL`/`PRISMREEL_ADMIN_PASSWORD`），上線前要手動在 VPS 的 `.env` 裡設定，不能只改本機 `.env.example`。

## 本 session 已完成、跟登入系統無關的另一件事（供對照，避免混淆）

同一輪對話裡使用者臨時追加了「繁體中文語系」需求，已獨立完成並上線（跟登入系統無依賴關係）：
- `frontend/messages/zh-Hant.json` 等改動，commit `4878172`
- 已 scp 同步到 VPS 並 rebuild，https://prismreel.soulo-ai.com/#/settings 已可見三語系切換
- 這件事已結束，不需要下一個 session 處理
