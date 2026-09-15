---
name: feedback-official-character-library-thumbnail-and-count-fix-2026-09-15
description: 2026-09-15交接時使用者回報的2個問題（第1張破圖、角色清單不完整）根因與修復結果
metadata:
  type: feedback
---

## 問題1：官方角色分頁「第1張破圖」

**根因**：非程式邏輯問題。圖片本身一直正常（源站+後端 200 OK），是 Cloudflare edge cache 把部署完成前某次探測請求拿到的 404 快取住了 24 小時。詳見 [[feedback_cf_edge_cache_stale_404_during_deploy_window]]。

**修復**：CF Dashboard 自訂清除該 URL 快取，5秒內生效，live 驗證圖片 200 OK image/jpeg。

**順手補的防護**：`AssetPickerModal.tsx` 的 `<img>` 加上 `onError` handler，載入失敗時 fallback 成文字卡片（人形 icon + 國籍/職業標籤），而非讓瀏覽器原生破圖 icon 直接暴露給使用者。未來若同類 CF 快取競態再發生，至少 UI 不會顯示破圖。

## 問題2：「角色未完全」

**根因**：不是資料欄位缺失，是總數判斷錯誤——前一 session 只抓到60筆就以為抓完了，但官方 Digital Character Library 遠遠不止60筆。重新用瀏覽器 React fiber tree 滾動抓取（同一套手法，見 [[reference_seedance_real_person_face_restriction_and_asset_library]]），累積到 **510 筆**才停止（尚未確認是否真正到底，只是達到使用者同意的合理上限）。

**抓取踩坑**：虛擬滾動列表會把已抓過的角色重新排列顯示（可能是隨機排序或洗牌機制），單純用「畫面上看到新名字」判斷是否為新角色不可靠——必須用 SID/asset_id 做集合去重，且連續多次「0新增」不能當作「已到底」的訊號，要滾動更多次確認（本次案例中連續2次0新增後，第3次又新增了30筆）。

**縮圖現狀（2026-09-15持續更新）**：510筆中目前120筆（原60+8+新增52）有實際縮圖檔案，其餘390筆依賴前端 `onError` fallback 顯示文字卡片（使用者已同意此權宜方案）。同日稍後使用者主動要求「拉回完整縮圖」，抓取+下載+壓縮手法已驗證可重複執行，但下載環節有渲染器凍結瓶頸（見 [[feedback_browser_blob_download_freezes_renderer_after_few_calls_2026-09-15]]），工具呼叫數與張數概略1:1，390筆仍需多輪session接續。

## 已知教訓

背景下載縮圖過程中誤刪了已完成的77張暫存縮圖，造成一次浪費；根因與規則見 [[feedback_never_delete_unmoved_downloaded_artifacts_as_cleanup]]（workspace 層級記憶，跨專案通用）。
