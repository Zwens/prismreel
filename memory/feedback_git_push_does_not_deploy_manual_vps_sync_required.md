---
name: git-push-does-not-deploy
description: git push 到 GitLab 不會觸發 prismreel.soulo-ai.com 自動部署，需手動 SSH 進 VPS 同步+重build
metadata:
  type: feedback
---

git push 到 GitLab（`gjseo.qit1.net/prismreel`）**不會**讓 https://prismreel.soulo-ai.com 自動更新。

**Why**：VPS（`vps_main`，202.182.117.182）上的 `/opt/prismreel` 部署目錄不是 git repo（沒有 `.git`），是用手動複製方式建立的獨立副本，跟本機/GitLab 的 git 歷史完全脫鉤。repo 裡也沒有 `.gitlab-ci.yml`，沒有任何 CI/CD 自動部署管線。2026-09-08 第一次在這個專案做改動時，commit+push 完就跟使用者報告「完成」，使用者實際打開 live 網址完全看不到更新，才發現這個落差。

**How to apply**：
1. 任何要讓 https://prismreel.soulo-ai.com 生效的改動，git push 完後還要額外執行：
   - `scp` 把改動過的執行期檔案同步到 `vps_main:/opt/prismreel/<相同相對路徑>`（不要整包覆蓋，避免動到 VPS 上的 `.env`、`output/` 使用者資料）
   - SSH 到 VPS，`cd /opt/prismreel && docker compose build frontend`（前端有改動時）或 `backend`（後端有改動時）
   - `docker compose up -d <service>` 套用新 image
   - 打 live 網址驗證（curl 檢查 JS bundle 內容 + 瀏覽器實際渲染畫面，兩者都要做，見 [[lockfile-must-regenerate-in-build-env]] 附帶的教訓：bundle 有字串不代表功能完整生效，要連 chunk 一起查）
2. 完成任何「使用者看得到的變更」前，不要只憑「已經 commit+push」就回報完成——必須實際打開 live URL 驗證。
3. 若之後這個專案設定了正式 CI/CD（`.gitlab-ci.yml` 或 webhook），這條記憶要更新/作廢，先查證有沒有新增再照舊流程做。
