---
name: feedback-browser-blob-download-freezes-renderer-after-few-calls-2026-09-15
description: claude-in-chrome透過javascript_tool連續多次fetch+Blob下載，2-3次後CDP會timeout導致渲染器凍結；縮圖批量抓取時的已知瓶頸
metadata:
  type: feedback
---

## 現象

用 `javascript_tool` 在頁面內執行 `fetch(url).then(blob)` + `<a download>` 觸發瀏覽器下載，單次呼叫必須成功；但同一個 `javascript_exec` 呼叫內若寫迴圈連續下載多張（即使中間加 `setTimeout` 間隔），跑到第2-3張左右就會遇到 `CDP sendCommand "Runtime.evaluate" timed out after 45000ms` 或 `Page.captureScreenshot timed out`，渲染器進入凍結狀態，需要手動 `wait` 幾秒才能恢復回應。

**根因未查證**：不確定是 blob URL 未即時 revoke 累積記憶體、Chrome 下載佇列本身有頻率限制、還是 CDP 連線在連續下載時被下載對話框/瀏覽器內部佇列卡住。本次未深入排查，只找到迂迴解法。

## 已驗證的迂迴解法

改成「每次 `javascript_tool` 呼叫只下載 1 張」，一張一張獨立呼叫，不在單次執行裡寫迴圈。呼叫之間天然有工具往返的間隔時間，足以讓渲染器不凍結。**代價**：工具呼叫數與目標張數 1:1，批量抓取時（如本次52張）會消耗大量輪次。

## 相關前置條件

Chrome 對同網站連續多次「非使用者直接點擊觸發」的下載，預設會靜默擋下（下載動作看似執行成功但檔案不落地），需要使用者手動在網址列鎖頭圖示或 `chrome://settings/content/automaticDownloads` 把該網站加入自動下載允許清單，才能讓 `<a download>` 觸發的下載真正寫入磁碟。此為下載成功的必要前提，與凍結問題是兩個独立障礙。

## How to apply

下次需要批量下載檔案（縮圖、附件等）透過 claude-in-chrome 時：
1. 先確認該網站的自動下載權限已開啟
2. 不要嘗試在單次 `javascript_exec` 裡寫下載迴圈，一律拆成一張一張單獨呼叫
3. 若張數 > 50，先跟使用者說明「每張約需一次工具呼叫」的量級，讓對方決定是否分批執行或找替代方案（如改用有官方 API 的下載途徑，若存在的話）
