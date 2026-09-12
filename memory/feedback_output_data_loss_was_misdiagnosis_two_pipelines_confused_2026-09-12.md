---
name: output-data-loss-was-misdiagnosis-two-pipelines-confused-2026-09-12
description: 2026-09-11判定的「VPS資料遺失」經2026-09-12重查證實為誤判——是ComicGen與Playground兩條獨立產線被當成同一份資料查證所致
metadata:
  type: feedback
---

2026-09-11交接記錄判定 VPS `output/projects.json` 不存在、`assets/uploads/video` 皆0檔案為「核心創作資料遺失」，2026-09-12重查後證實是誤判：查證時只看了 `output/assets/`、`output/uploads/`、`output/video/` 這幾個 ComicGen（漫畫生成）專用的舊路徑（確實一直是空的，因為這台 VPS 從未有人成功用過 ComicGen 建立專案），完全漏看 Playground（影片生成）真正落地的資料在 `output/playground/`（`playground_history.json` + `videos/uploads/thumbnails` 子目錄），且截至查證當下持續有新資料寫入。手動 `fetch('/playground/history')` 帶登入 cookie 直接證實 API 回傳完整10筆歷史紀錄，資料從未丟失。

**Why**：這個產品實際上是兩套獨立系統拼在一起（ComicGen 結構化角色/場景/道具管理 + Playground 自由生成沙盒），但前端導覽只用「工作區/資產庫/創作台」三個模糊詞，沒有任何提示告知使用者這是兩個不共享資料的世界。連 AI 自己第一輪查證都被這個命名結構帶偏，把「創作台裡其實有資料」誤判成「工作區/資產庫沒資料=遺失」。

**How to apply**：
1. 查任何「資料是否遺失/為何顯示空」類問題前，先確認清楚使用者實際操作的是哪一個功能分頭，不要只看表面上「畫面空的」就直接假設資料層出問題——先用該功能對應的 API 端點（不是猜測的資料路徑）直接驗證。
2. 已於2026-09-12把 workspace/library/playground 三分頁重新命名為「漫畫生成/素材庫/影片生成」並新增獨立「生成歷史」分頁（直接重用 PlaygroundPage 的 ResultGallery），從根本解決命名落差——見 `feat/nav-rename-and-history-tab` 分支 commit。
3. 若未來仍遇到「哪個分頁該有哪些資料」混淆，先確認是 ComicGen 產線（`output/projects.json`/`series.json`/`library_assets.json`，經 `AssetLibraryPage.tsx` 呈現）還是 Playground 產線（`output/playground_history.json`，經 `ResultGallery`/`PlaygroundHistoryPage.tsx` 呈現），兩者資料完全不互通，除非使用者在 Playground 手動點「存到資產庫」（`save-to-library` 端點）。

原始交接記錄 `project_output_data_loss_handoff_2026-09-11.md` 已刪除（結論已在此收斂，無後續待辦）。
