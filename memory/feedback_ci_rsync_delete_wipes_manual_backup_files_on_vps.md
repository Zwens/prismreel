---
name: feedback_ci_rsync_delete_wipes_manual_backup_files_on_vps
description: GitLab CI部署腳本用rsync -a --delete同步到VPS，手動在VPS上建立的.bak備份檔案會在下次CI部署時被清掉
metadata:
  type: feedback
---

2026-09-16 在 VPS `/opt/prismreel/.env` 改動前照六步SOP慣例做了 `cp .env .env.bak.$(date +%Y%m%d%H%M%S)` 備份，`requirements-docker.txt` 同樣做了備份。下次 `git push` 觸發 CI 部署後回頭確認備份檔，兩份都已消失。

**根因**：`.gitlab-ci.yml` 的 `deploy_production` job 用 `rsync -a --delete ./ /opt/prismreel/`，`--delete` 語意是「讓目的地與來源完全一致，來源沒有的檔案，目的地也刪掉」。手動在 VPS 上建立、不存在於本機 git repo 裡的任何檔案（包含 `.bak` 備份），只要不在 `--exclude` 清單裡就會被下一次部署清掉。目前 exclude 清單只有 `.git`/`.env`/`.env.local`/`output/`/`frontend/.env.local`/`frontend/node_modules/`。

**Why**：這台 VPS 用 rsync+CI 全量部署（非傳統只 `git pull` 增量更新），跟 spheretap/funbchk 等純手動 SSH 操作的專案部署模式不同，既有「修改前先備份」的通用習慣在這裡不完全可靠。

**How to apply**：
1. 在這個專案（或任何 `rsync --delete` 部署管線）改 VPS 上的檔案前，若該檔案本身不在 CI exclude 清單裡（如 `requirements-docker.txt`），備份要嘛存到 exclude 清單涵蓋的路徑（如 `.env.bak` 若不小心用 `.env` 開頭前綴可能被誤判，需查清單是精確比對還是前綴比對），要嘛直接改本機 git 檔案走正規 commit/push 流程（這樣改動本身就在 git history 裡留痕，不需要額外備份檔）。
2. 這次的正確作法（已驗證安全）：`requirements-docker.txt` 直接在本機改、commit、push，不在 VPS 上直接編輯，備份需求由 git history 天然滿足。`.env` 因為在 exclude 清單內不受 `--delete` 影響，VPS 上直接改是安全的，但那份手動 `.bak` 副本同樣不安全，下次應改用 `git diff` 記錄舊值或直接記錄進 memory 文字，而非依賴檔案系統備份。
