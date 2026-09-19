---
name: feedback_env_config_dialog_writes_global_env_not_per_account_2026-09-18
description: 「環境配置」彈窗（EnvConfigDialog）POST /config/env寫入的是專案根目錄全域.env檔，非單一帳號/session獨立配置；用假key跨過彈窗會覆寫使用者真實金鑰且無git版控可復原
metadata:
  type: feedback
---

## 事故經過
驗收 MediaInput.tsx 本地上傳還原（見 [[feedback_media_input_upload_removed_beyond_user_intent_2026-09-18]]）時，
瀏覽器自動化每次路由切換都被「環境配置」必填彈窗卡住（`EnvConfigChecker.tsx`每次組件掛載都重新
`GET /config/env`檢查`GEMINI_API_KEY`是否非空）。為了跨過彈窗，直接呼叫
`POST http://localhost:17177/config/env`帶測試假值（`AIzaSy...`格式，非真實key），
**未預期**這個端點寫入的是專案根目錄`.env`檔（`Configuration saved to .../.env`），把使用者真實的
`GEMINI_API_KEY`永久覆寫成假值。`.env`在`.gitignore`中不受版控，動手前也沒手動備份，導致原值完全遺失，
靠使用者自己記得或去 Google AI Studio 重新產生才復原。

## 🔴 核心教訓：任何「填表單/存設定」動作，動手前必先確認寫入目的地與作用域
不能假設「登入後的帳號設定」只影響自己這個 session/帳號——`EnvConfigDialog`介面文案完全沒有提示
「這是全域專案配置，會影響所有使用者」，UI 呈現方式（個人化的設定彈窗）容易讓人誤判為 per-account。
**遇到「必填欄位」擋住操作、想用假值/測試值跨過時，動手前必須先查證該欄位儲存端點的實際寫入目的地
（尤其是否為共用/全域檔案），不能只因為「這只是為了讓UI跑起來」就假設影響範圍侷限於當下操作。**

## Why
這台機器上同時有多個 peer session 在跑（`ListAgents`顯示 5 個並行 busy session），任何一個都可能正在
用真實 Gemini API Key 執行付費生成任務。全域`.env`被覆寫會讓這些任務立即開始用假 key 呼叫失敗，且因為
`.env`不受版控，一旦覆寫沒有留存原值就無法程式化復原，只能依賴使用者記憶或第三方後台重新產生金鑰。

## How to apply
1. 任何「設定/配置」類 UI 彈窗，動手填入測試值前，先 grep 該表單送出的 API 端點後端實作，確認
   寫入目的地是 per-user DB record 還是共用檔案（`.env`/共用 config 檔）
2. 若確認是共用/全域配置，且原本已有值（非空）→ 視同 CLAUDE.md §1「不可逆/影響共享系統」動作，
   動手前必先讀取並记录當前值（哪怕只是複製到 scratchpad 暫存），才能安全復原，或直接改問使用者
   要不要在他自己的瀏覽器操作
3. UI 驗收被必填彈窗卡住且找不到繞過方法時，優先選項是請使用者提供一個可用於本機測試的 key（哪怕
   額度很小），或改用純程式碼審查+靜態確認交付，而非用假值硬闖共用配置端點
4. 本次教訓也提醒：`curl`/`fetch`探測後端行為前，若該操作是 POST/寫入類，須先確認是否有「唯讀先探測」
   的替代方式（如只 GET 不 POST），不能因為方便測試就直接對可能有副作用的端點送出假資料

## 相關
[[feedback_media_input_upload_removed_beyond_user_intent_2026-09-18]] — 本次驗收的原始任務
