---
name: feedback-env-config-settings-duplicate-surfaces-must-sync
description: EnvConfigDialog.tsx 與 SettingsPage.tsx 是兩份平行、獨立維護的環境設定表單，共用同一組後端欄位，改一處必查另一處
metadata:
  type: feedback
---

`src/components/project/EnvConfigDialog.tsx`（首頁/專案頁彈窗，供 `EnvConfigChecker.tsx` 首次啟動強制填寫）與 `src/components/settings/SettingsPage.tsx`（Settings → API 密鑰分頁）是兩份幾乎重複的環境設定表單，各自獨立定義 `EnvConfig` 型別、`DEFAULT_CONFIG`、`ENDPOINT_PROVIDERS`，但共用同一個後端 `api.getEnvConfig()`/`api.saveEnvConfig()`。

**Why**：2026-09-10 補 Ark/Seedance API Key 表單缺口任務中，交接記憶只判定「`EnvConfigDialog.tsx` 完全沒有 Ark Key 欄位」，實際查證發現 `SettingsPage.tsx` 早已有完整的 Ark Key 表單（Key 輸入框+Intl/CN 地區按鈕），只是同樣漏了 `ARK_BASE_URL` 端點。若只信任單一交接記憶的判定，會漏改另一個表單，造成兩處欄位不同步。

**How to apply**：日後任何要在其中一個環境設定表單新增/修改欄位的任務，動手前先 Grep `EnvConfigDialog.tsx`/`SettingsPage.tsx` 兩份檔案確認欄位現況，不要只信任其中一份的既有判定或交接記憶；改動時兩處同步處理，除非有明確理由只改一處。
