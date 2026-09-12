---
name: gitlab-ci-auto-deploy-setup
description: PrismReel 2026-09-11起改用 GitLab CI 自動部署 main 分支到 VPS，取代手動 scp+docker build 流程
metadata:
  type: feedback
---

`.gitlab-ci.yml` 已加入 repo 根目錄，`merge 到 main` 時自動觸發部署，不再需要手動 scp+docker build（見 [[feedback_git_push_does_not_deploy_manual_vps_sync_required]] 的舊流程，現已由此取代）。

**運作機制**：VPS（202.182.117.182）上原本就有一個 GitLab Runner（`vps-shell-runner`，shell executor，連到 `gjseo.qit1.net`，無 tag 限制，其他專案共用），CI job 直接在這台 runner 上跑：
1. `rsync -a --delete`（排除 `.git`/`.env`/`output/`/`node_modules`）把 repo 內容同步到 `/opt/prismreel`
2. `docker compose build backend frontend`
3. `docker compose up -d backend frontend`

**前置權限修復（2026-09-11 已做過，若未來 runner 重裝需重做）**：`gitlab-runner` 系統使用者原本沒有 `/opt/prismreel` 寫入權限、也不在 `docker` group，導致 CI job 必定失敗。已執行：
```
chown -R gitlab-runner:gitlab-runner /opt/prismreel
usermod -aG docker gitlab-runner
systemctl restart gitlab-runner   # group membership需要重啟daemon才生效
```

**Why 選 merge-to-main 觸發（非任何分支push）**：feature branch push 不該影響 production；main 才是部署基準線，避免未經 review 的分支內容意外上線。

**How to apply**：以後功能開發完 MR 合併進 `main` 即會自動上線，不用再手動 scp。若要確認這次部署是否真的跑完，查 GitLab 該次 MR 頁面的「流水線」狀態，或 `ssh vps_main "docker ps --format '{{.Names}}\t{{.CreatedAt}}'"` 看容器建立時間是否等於合併時間附近。CI job 失敗時，錯誤多半出在 rsync 權限或 docker 權限，先查 `gitlab-runner` 使用者身份能否寫入 `/opt/prismreel` 與操作 docker。
