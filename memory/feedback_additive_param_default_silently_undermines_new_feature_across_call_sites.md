---
name: additive-param-default-silently-undermines-feature
description: 新增 Optional[str]=None 這類「不破壞既有呼叫」的附加參數時，必須逐一核對每個既有呼叫點是否該傳入新值，不能只驗證新參數本身邏輯正確
metadata:
  type: feedback
---

2026-09-11 用量追蹤功能實作（`ScriptProcessor` 9 個方法加 `user_id: Optional[str] = None`）中，per-task code review 全部通過（9 個方法各自的呼叫端都各自看起來正確），但最終全分支審查（用最強模型做跨任務整合檢查）額外抓出 3 處遺漏：`pipeline.py:extract_preview`、`pipeline.py:reparse_project`、`api.py:analyze_script_for_styles` 這三個呼叫點雖然作用域內明明有 `owner_id`/`script.owner_id` 可用，卻忘記傳給底層方法，導致這幾條路徑的用量被記到空字串（`""`／`"unknown"`）而非正確使用者。另外 `import_file_and_split` 新增的 `owner_id` 參數被上層方法定義了卻從未被唯一呼叫端傳入，成為死參數。

**Why**：`Optional[X] = None` 這種「向後相容、不破壞既有呼叫」的參數設計，正是它的安全性讓遺漏變得不明顯——不傳就是預設值，不會報錯也不會測試失敗，只會默默記到錯的地方或完全不記錄。任務被拆成「改方法簽名」（Task 4）與「接通呼叫端」（Task 6）兩個獨立 task 時，Task 6 的 brief 用「列舉」方式指定要改哪幾個呼叫點（而非用「找出所有呼叫這個方法的地方」這種窮舉式要求），本身就會系統性遺漏 brief 撰寫當下沒想到的呼叫點。單一任務的 code review 只驗證 brief 列出的範圍改得對不對，看不到 brief 本身列漏了誰。

**How to apply**：
- 任何「加一個帶預設值的參數、讓既有呼叫不用改」的重構，寫 brief/plan 時不要用「這幾個呼叫點要改」的列舉方式，改用「grep 出所有呼叫這個方法的地方，逐一核對」的窮舉方式，並把 grep 指令本身寫進 brief 讓 implementer 或 reviewer 能重新跑一次核對數量
- 這類「新增可選參數、影響多個既有呼叫點」的變更，若走 subagent-driven-development 這類多任務拆分流程，**最終全分支審查絕不可省略**——這正是這次抓出問題的唯一一關，單任務審查在結構上看不到「整條清單本身不完整」這件事
- 驗收這類 threading 任務時，除了確認「新參數的邏輯本身正確」，還要額外自問一句「有沒有既有呼叫點作用域內明明有值可傳、卻沒傳」，這是 code review checklist 裡容易被跳過的一類 Important 發現
