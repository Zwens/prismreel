---
name: rm-rf-output-deletes-tracked-assets
description: worktree內測試完清理殘留時用rm -rf output/會連同版控管理的素材檔案(presets/bgm等)一起刪掉，需精確指定路徑
metadata:
  type: feedback
---

2026-09-11 在 `.worktrees/playground-usage` 測試 `usage_repo.py` 寫入邏輯時，測試腳本會在該 worktree 產生 `output/auth.db`，測試後用 `rm -rf output/` 清理，結果連同版控管理的 `output/presets/bgm/*`（8 個 BGM 音樂素材檔案 + LICENSES.md）一起刪除，變成 unstaged deletion。靠提交前的 `git status --short` 例行檢查才發現，用 `git restore output/presets/` 救回，未造成實際損失。

**Why**：這個專案的 `output/` 目錄是「版控素材（presets/）+ 執行期產物（auth.db、playground/uploads/ 等）混雜」的結構，不是純粹的 gitignore 產物目錄；`rm -rf` 這種目錄層級清除動作預設不會意識到裡面混了兩種性質完全不同的內容。

**How to apply**：
- 清理測試殘留時，一律精確指定要刪的檔案/子目錄路徑（如 `rm -f output/auth.db`），禁止對整個 `output/` 做 `rm -rf`
- 任何刪除動作後、commit 前，`git status --short` 是強制檢查點——看到非預期的 `D` (deleted) 標記要先 `git restore` 而非直接 commit
- 這個坑點跟 CLAUDE.md 既有的「刪除前先讀再動」原則同一類，但這次是自己測試產生的路徑習慣性誤判為「純暫存」，值得單獨記一筆提醒範圍判斷要更保守
