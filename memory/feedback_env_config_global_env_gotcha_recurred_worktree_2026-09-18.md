---
name: feedback_env_config_global_env_gotcha_recurred_worktree_2026-09-18
description: 已知「環境配置彈窗寫入全域.env」的坑在獨立worktree場景下重演，誤判為worktree間process衝突導致大量無效排查
metadata:
  type: feedback
---

## 事故經過
擔任 `feature/video-workflow-multi-shot` 分支的獨立稽核官，跑瀏覽器 E2E 驗證時被「環境配置」必填彈窗卡住。
使用者在瀏覽器貼上真實 Gemini API Key 並點「儲存配置」，畫面卡住重置為空。**完全沒有意識到
[[feedback_env_config_dialog_writes_global_env_not_per_account_2026-09-18]] 這條舊記憶已經記載過同一個
端點的架構事實**，反而花了一大輪時間排查「為什麼 worktree backend 寫入了主 repo 的 .env」——嘗試了：
- 檢查 port 17177 是否被多個 process 搶佔（`netstat`/`Get-NetTCPConnection` 結果反覆矛盾，疑似殭屍 socket）
- Kill 掉主 repo 殘留的 backend process（688/31032），事後才驚覺沒先確認是否為他人 session 在用
- 重啟自己 worktree 的 backend 多次，每次都用 `python -c` 隔離驗證 `get_user_config_path()` 邏輯本身完全正確
- 最終仍然复现同樣結果：worktree backend 回報「Configuration saved to ...AI 短片系統 Prismreel\.env」

真正原因：這個端點的設計就是「專案根目錄全域 .env」，**與 worktree 是哪一個完全無關**——即使
backend 進程確實是從 worktree 的 `api.py` 啟動、`get_user_config_path()` 的 `__file__` 推導路徑
邏輯在 worktree 內部完全正確，只要它讀到的 project_root 是某個特定寫死或環境變數指定的路徑（本案
實際指向主 repo 目錄），就會一直寫到那裡去，不會因為「我在哪個 worktree 執行」而改變。

## 🔴 核心教訓：先查現有 memory 再排查「反常」現象，不要把已知架構限制當成新 bug 去深挖
1. Session 開頭/踩到卡點時，**先 Grep 專案 memory 目錄的關鍵字**（本案：「環境配置」「config/env」
   「.env」），再決定要不要展開技術排查。這條舊記憶就在 `AI 短片系統 Prismreel/memory/MEMORY.md`
   第13行索引，本應在踩到彈窗卡住的第一時間就浮現。
2. worktree 場景下，任何寫入本機檔案系統的端點都要先假設「可能沒有 per-worktree 隔離」，尤其是
   `.env`/config 類全域狀態，不要預設「backend 進程跑在 worktree 目錄下 = 寫入也隔離在 worktree 內」。
3. 排查「backend 行為與隔離驗證結果不一致」這類謎團前，先花 1 分鐘 grep memory 常常比一小時的
   process/socket 底層排查更快找到答案——本案至少省下 30+ 分鐘的 netstat/Get-NetTCPConnection 折騰
   與一次不必要的 kill 陌生 process 動作（688/31032 是否屬於其他 session 至今未完全確認）。

## Why
獨立稽核官這個角色的價值在於快速、準確地驗收，不是重新發現已知問題。花時間在「已經有人踩過且記錄
在案」的坑上，既浪費使用者等待時間，也讓「稽核」本身的可信度打折——如果連查自己專案 memory 這一步
都漏做，使用者難以信任後續「Task 10 E2E 驗證」的結論品質。

## How to apply
- 任何本機開發環境卡點（彈窗、必填欄位、儲存失敗、重啟無效）→ 動手排查前先 Grep 該專案
  `memory/MEMORY.md` 全文，關鍵字用使用者原話 + 功能名稱兩種都要試
- 確認是已知坑之後，直接引用舊記憶的 How to apply 段落照做，不要重新發明排查流程
- 若排查了一段時間才發現是已知坑，事後要在新記憶檔案裡明確寫「重演」二字並連結舊記憶，方便下次
  追蹤同類坑的重演次數（機率性遵守率低的訊號，可能需要往結構性防呆方向想，而非單純記文字規則）

## 相關
[[feedback_env_config_dialog_writes_global_env_not_per_account_2026-09-18]] — 原始事故記錄，本次已重演
