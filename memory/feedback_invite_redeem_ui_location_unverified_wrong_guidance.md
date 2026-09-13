---
name: invite-redeem-ui-location-unverified
description: 未查前端頁面結構就對使用者說「登入頁可輸入邀請碼」，實際是獨立 /redeem?code= 頁面
metadata:
  type: feedback
---

後端 `/admin/invites` 產生邀請碼後，未讀前端程式碼就直接告訴使用者「到登入頁輸入邀請碼」，被使用者當場指出「登入頁沒有這個欄位」才回頭查證。

**Why**：`frontend/src/app/login/page.tsx` 只有 email/密碼兩個欄位，完全沒有邀請碼相關 UI；真正的兌換入口是獨立路由 `frontend/src/app/redeem/page.tsx`，透過 URL query string `?code=` 自動帶入邀請碼，使用者只需填 email+密碼。兩個頁面是分開的路由，登入頁不會因為系統有邀請碼機制就自動長出對應欄位。這屬於 [[../../../.claude/projects/C--Users-chenc-Documents-Claude-Wmzic/memory/MEMORY-error-shapes.md]] 錯誤形狀#4 的變體——不是用了過期快照，而是完全沒有查證就依常識/慣例假設 UI 長相，本質同樣是「陳述現況前無 live 依據」。

**How to apply**：
- 任何「產生完後端資源（邀請碼、token、連結）該怎麼給使用者用」的指引，動手前先 Grep/Read 對應前端頁面實際結構（表單欄位、路由、query string 用法），不能用「這功能應該長在哪」的常識推測。
- 產生邀請碼類資源時，優先給使用者「完整可點擊連結」（如 `/redeem?code=xxx`）而非「裸邀請碼字串」，避免使用者自己在錯的頁面尋找輸入框。
