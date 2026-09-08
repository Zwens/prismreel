# PrismReel MEMORY Index

> 進入本專案工作時 Read 載入。工作區共用規則見根目錄 CLAUDE.md。

## 部署機制（🔴 最重要，動手前必讀）
- [**🔴 git push GitLab 不會自動部署，VPS 是手動複製非 git clone**](feedback_git_push_does_not_deploy_manual_vps_sync_required.md) — 2026-09-08首次踩坑；更新 prismreel.soulo-ai.com 必須 scp 同步檔案 + VPS 上 docker compose build+up
- [**VPS lockfile 需在 node:20-alpine 容器內重新產生，本機 npm 版本不相容**](feedback_lockfile_must_regenerate_in_build_env_container.md) — 本機npm11 vs VPS build用npm10，package-lock.json 格式差異導致 npm ci 失敗

## 專案基本資訊
- 產品：AI Comic Generator / PrismReel Studio，文字腳本→漫畫式短片產製平台
- 技術棧：Next.js 14 App Router 前端 + FastAPI 後端，Docker Compose 部署
- Live 站台：https://prismreel.soulo-ai.com （容器：prismreel-frontend / prismreel-backend）
- VPS：`vps_main`（202.182.117.182，SSH config 別名），部署目錄 `/opt/prismreel`
- 本機開發目錄：`AI 短片系統 Prismreel/`（也是一個獨立 git repo，remote origin 指向 GitLab `gjseo.qit1.net`，非 VPS 真正吃的來源）
- 桌面單機模式（`python main.py`）與 VPS 多用戶部署模式並存，改動時注意兩者行為差異

## 待辦：多租戶登入系統
- [**登入系統實作交接**](project_auth_handoff.md) — spec 已寫好待審閱，下一 session 接手實作
