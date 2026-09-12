---
name: handoff-claims-implemented-but-uncommitted
description: 跨session交接檔稱「已完整實作+curl驗證通過」不等於已commit，worktree可能仍是unstaged狀態
metadata:
  type: feedback
---

2026-09-11 用量追蹤功能秒數/規格改動交接，上一個 session 的交接檔寫「已完整實作，後端curl驗證通過」，但接手後 `git status` 發現 13 個檔案全是 unstaged 異動，commit log 停在更早的 commit，這些改動從未進版控。行為本身（curl 驗證的功能）是真的做了，但「完成」的定義被交接者無意間窄化成「功能可運作」，漏了「已固化進 git 歷史」這一層。

**Why**：工作階段內反覆測試/修改很正常，session 中途改完就急著 curl 驗證、驗證通過就當作「這個任務段落」結束，commit 這個動作被視為理所當然的收尾但其實被忘記做。

**How to apply**：接手任何「上一個 session 已完成 XXX」的交接時，`git status`/`git log` 是第一步，不是最後一步——先確認交接檔描述的內容是否真的進了 commit，而不是先驗證功能行為再回頭補查版控狀態。同樣邏輯適用於「已 push」「已部署」等宣稱，動手前都要用工具查證當下版控/部署的實際狀態，而非直接採信文字敘述。
