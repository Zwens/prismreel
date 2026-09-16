---
name: ui-change-visual-verify-blocked-by-login-pattern-reuse-accepted
description: UI改動需截圖驗收但本機dev環境卡在登入頁時的處理方式
metadata:
  type: project
---

本機dev環境（localhost:3008）現在有登入頁擋在主應用前，未提供測試帳密時無法自動化截圖進入主頁面觸發 Modal。

**Why**：2026-09-16 HANDOFF.md item③（Playground/Modals對齊Line B）收尾時，claude-in-chrome 導航後 tab context 查詢矛盾（回報成功但仍顯示 chrome://newtab/），改用 Playwright MCP 導航正常但落地在 `/login`；使用者選擇不提供憑證，改用「與已驗證過的 `PlaygroundPage.tsx` 完全相同的 class 寫法」作為風險依據，跳過視覺驗收直接 push。

**How to apply**：往後本專案UI改動若命中登入頁擋截圖，先問使用者是否提供測試帳密／自己驗證／接受「複用已驗證pattern」跳過視覺驗收三選一，不要自行嘗試繞過登入或假設有預設帳密。Playwright MCP 的 `browser_take_screenshot` 檔案輸出路徑限制在工作區根目錄內（`.playwright-mcp` 或工作區本身），不接受 temp scratchpad 路徑，需輸出到白名單過的 `screenshot/` 子目錄再事後清除。
