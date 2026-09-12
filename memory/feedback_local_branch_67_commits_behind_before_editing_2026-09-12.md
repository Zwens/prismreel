---
name: local-branch-67-commits-behind-before-editing-2026-09-12
description: 動工前未核對本機分支與遠端main的落差，導致對著已被遠端取代的舊版api.ts重複寫了一份用量追蹤函式
metadata:
  type: feedback
---

2026-09-12在 `feature/multi-tenant-auth` 分支上直接改 `frontend/src/lib/api.ts` 前，沒有先跑 `git fetch && git log HEAD..origin/main` 確認落差，結果新增的 `getMyUsage`/`getAllUsersUsage` 函式跟遠端 main 早已存在、且更完整（多帶 model/resolution/input_has_video/duration 欄位）的同名函式撞名。本機 `main` 分支當時實際落後 `origin/main` 67 個 commit，`feature/multi-tenant-auth` 落後19個——整個 `app/usage/` 頁面、`user_repo.py`/`usage_repo.py` 等後端模組在本機工作目錄完全不存在，卻已經在VPS上線運作。

**Why**：本機這個 repo 有多個並行 feature 分支（`feature/multi-tenant-auth`、`feature/usage-tracking`、`feat/playground-usage-tracking`…），且此前 session 常態是直接在某個 feature 分支上繼續工作，未養成先跟 origin/main 同步的習慣。與 [[feedback_merge_commit_exists_but_content_not_ancestor_2026-09-11]] 是相關但不同的坑：那條是「merge commit 存在於歷史≠內容真的合併」，這條是「本機工作分支本身已經落後遠端多少都不知道」，兩者都會導致對著過時或錯誤的程式碼基礎做重複勞動。

**How to apply**：Standard/Critical 任務要修改一個既有檔案前，尤其該檔案屬於多人/多session協作的共用 repo，先跑 `git fetch origin && git log HEAD..origin/main --oneline` 快速確認本機分支落差。若落差 > 10個commit或涉及要改的檔案在落差範圍內，先評估要不要在最新 main 基礎上開新分支，而非直接在舊分支上疊加，避免重複造輪子或跟已上線版本衝突。修復方式：`git stash` 保留本次改動 → `git checkout main && git pull` → 基於最新 main 開新分支 → `git stash pop` 疊回改動並解衝突。
