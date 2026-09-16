---
name: fetch-blob-download-blocks-main-thread-large-video
description: ResultCard 下載按鈕用 fetch+blob 下載大型影片時同步阻塞主執行緒，畫面凍結無提示，使用者誤判「無法下載」
metadata:
  type: feedback
---

生成歷史列表頁（`frontend/src/components/modules/playground/ResultCard.tsx`）的下載按鈕原本用 `fetch(mediaUrl) → resp.blob() → URL.createObjectURL → a.click()`，對較大的影片檔（實測最大 28MB）會把整個檔案同步讀進記憶體，阻塞瀏覽器分頁主執行緒。使用者點擊後畫面完全無反應（無 loading、無下載提示），等再久也沒有跳出存檔對話框，體感等同「下載失敗」，但實際上請求本身有成功拿到 200。

**Why：** `resp.blob()` 是一次性讀完整個回應體才 resolve，檔案越大同步阻塞時間越長；claude-in-chrome 自動化截圖工具在這段期間連續 CDP `Page.captureScreenshot` 逾時報「renderer may be frozen」，正好印證了這個阻塞現象，不是自動化環境雜訊。

**How to apply：** 同源靜態檔案（`/files/...`）下載一律用原生 `<a href={url} download>` + `a.click()`，不要包 fetch+blob——瀏覽器會把整個傳輸交給自己的下載管理器背景處理，不占用頁面 JS 執行緒。`DetailPanel.tsx` 的下載按鈕本來就是這個寫法，是正確對照組；`ResultCard.tsx` 已於 commit `7e8338e`（2026-09-15）修正為一致寫法。日後任何新增下載按鈕，先看這兩個檔案的現行寫法，不要重新發明 fetch+blob 版本。

排查時的假訊號：用 `javascript_tool` 手動 `fetch(url, {method:'HEAD'})` 得到的 JS 回傳值（200）與 `read_network_requests` 記錄的瀏覽器真實網路層行為（503）互相矛盾——後者才是可信來源，`javascript_tool` 內執行的 fetch 結果不能直接採信，尤其牽涉 headers/cache 的判斷。詳見 [[MEMORY-tool-design-gotchas]] 分類。
