---
name: push-must-check-all-configured-remotes
description: push完main只確認觸發CI部署的origin(GitLab)，忽略了同時存在的github備份remote，導致落後21個commit直到使用者主動查問才發現
metadata:
  type: feedback
---

DeeVid provider整合這輪工作（8任務SDD計畫+2輪安全修復+API Key UI+額度校正功能，共9個commit、5次push）全程只`git push origin main`（GitLab，觸發CI自動部署到VPS），從未檢查或推送`github`這個第二個已設定的remote，直到使用者主動問「gitlab和github都已經更新了嗎」才用`git ls-remote`查出GitHub落後21個commit。

**Why**：本專案`git remote -v`同時列出`origin`（GitLab，`gjseo.qit1.net`）與`github`（`github.com/Zwens/prismreel`）兩個remote。日常任務只在意「live網站有沒有更新」，而觸發部署的只有GitLab，導致push動作的注意力完全集中在origin，github變成心智盲區。[[feedback_video_workflow_merge_to_main_and_deploy_2026-09-19]]那次雖然有做雙remote同步，但那是單次執行結果，並未沉澱成「每次push main都要檢查全部remote」的固定規則，這次就沒有延續。

**How to apply**：
1. 任何`git push origin main`（或推送到觸發CI/部署的那個remote）完成後，順手跑一次`git remote -v`列出全部已設定的remote，逐一用`git ls-remote <remote> main`比對是否與本機HEAD一致
2. 發現落後的remote，先問使用者是否要補推（不同remote可能有不同用途，如GitHub可能是刻意的公開/私有分流，不可自行假設一定要同步），使用者確認後才push
3. 若一個session內會做多次push（如這次的連續多輪commit），不需要每次都檢查全部remote，但在session收尾（`/plan-end`）或使用者主動詢問部署狀態時，必須把「有幾個remote、各自最新commit是否一致」納入驗收範圍，不能只看觸發部署的那一個
