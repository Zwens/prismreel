---
name: feedback_worktree_auth_db_never_initialized_on_fresh_env_2026-09-19
description: 全新git worktree或全新本機環境第一次啟動prismreel後端，output/auth.db是空檔案且無表，所有登入相關API一律503
metadata:
  type: feedback
---

`src/apps/comic_gen/api.py` 的 app startup 流程從未呼叫
`auth_db.init_schema()`（該函式定義在 `src/apps/comic_gen/auth_db.py`，
只在各個 `test_*.py` 測試檔案裡被呼叫）。全新環境第一次啟動時，
`get_connection()` 用 `sqlite3.connect()` 會自動建立一個 0 bytes 的
`output/auth.db` 檔案，但完全沒有 `users`/`invites`/`usage_events` 表，
導致任何觸發 `enforce_login` middleware 的請求都拋
`sqlite3.OperationalError: no such table: users` → 500 中介層攔截後
變成前端看到的 503。

**Why**：VPS production 資料庫應該是很久以前就已建過表（正常運作中），
所以線上從未踩過這個坑；本機新 worktree/全新 clone 才會第一次啟動就壞。

**How to apply**：全新環境第一次啟動 prismreel 後端卡在「載入配置失敗」
或任何 API 503 時，先查後端 log 是否有 `no such table: users`，不要
predefault 往環境變數/網路連線方向排查。臨時解法（本機開發用途）：
```python
import sys; sys.path.insert(0, 'src')
from apps.comic_gen import auth_db, user_repo
auth_db.init_schema(auth_db.get_connection())
user_repo.create_user('you@local.dev', 'password', role='admin')
```
`output/` 整個目錄在 `.gitignore` 排除，這個修復不會進版控也不影響VPS。
根本修復（在 `api.py` app startup 補呼叫 `init_schema()`）屬於程式碼
變更，本次稽核範圍外未處理，需另行評估。

## 相關
[[project_video_workflow_e2e_task10_completed_2026-09-19]]
