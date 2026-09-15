---
name: feedback-official-character-thumbnail-root-cause-no-virtualization-permanent-fallback-2026-09-15
description: 官方角色縮圖大量顯示假人icon的真正根因與根治修復（非CF快取問題，是前端一次性渲染480張img+onError永久不重試）
metadata:
  type: feedback
---

## 使用者回報 vs 前一輪session的誤判

前一輪session（見 [[project_thumbnail_backfill_handoff_2026-09-15]]）宣稱「450/480縮圖已補齊，剩30筆線上庫已下架」並已結案。使用者實測「還是只有看到少量縮圖」，直接指出如果是loading那就是沒壓縮圖片——這個假設本身不對（本機縮圖平均6KB，早已壓縮），但使用者堅持有問題、拒絕接受「懶載入正常運作」的解釋，逼出了完整重新查證，才發現真正根因。

## 真正根因（兩層，缺一都不算根治）

1. **那30筆從未下架**：用ModelArk Playground的搜尋欄位（`Enter portrait gender, age, nationality search`）直接查asset_id，30筆100%命中，證實前一輪「15輪滾動0命中→判定已下架」的方法論本身有問題（滾動抓取跟搜尋查詢是兩種不同的可靠度，滾動漏抓不代表真的不存在）。

2. **前端`AssetPickerModal.tsx`一次性渲染全部480個`<img>`標籤，`onError`觸發一次就永久記錄進`failedThumbnails` state，不重試**。實測480張中137張顯示永久fallback（遠超過真正缺圖的30筆），但那些「fallback」的縮圖本機+live站台實際都是200正常——短暫的並發過載/CDN競態造成的一次性失敗被永久記住，沒有自癒機制。

**排查陷阱**：`document.querySelectorAll('img')`只能抓到還沒觸發onError的`<img>`，一旦onError切換成`<UserRound>` SVG fallback，`<img>`標籤直接從DOM消失，用`querySelectorAll('img')`統計會完全漏掉這批，容易誤判「圖片都在loading」。改用`button[title]`抓卡片本體，比對`querySelector('img')`有無存在，才能抓到真實的fallback比例。

## 根治修復（非治標補丁）

`AssetPickerModal.tsx`新增`CharacterThumbnail`子元件取代原本內聯的`<img>`+fallback邏輯：
1. **消除並發過載觸發源**：用`IntersectionObserver`（`rootMargin: 200px`）控制，卡片真正捲入可視範圍附近才掛載`<img>`，取代原生`loading="lazy"`在480個節點同時存在時判斷不夠精準的問題
2. **讓暫時性失敗自癒**：`onError`不再永久fallback，最多重試2次（`THUMBNAIL_RETRY_DELAY_MS=800ms`遞增延遲+cache-busting query string避開CDN快取鍵），重試耗盡才真正判定失敗顯示文字卡片

修復後live驗證：480張卡片中`svgFallback`穩定為0（相較修復前137），確認不再有永久假性失敗。

## How to apply

- 使用者對「看起來像bug」的堅持比自己第一輪的技術解釋更可信時，不要用「這是正常懶載入」搪塞，要重新用工具驗證，不能假設自己已查清
- 修「症狀」（重試）跟修「觸發源」（虛擬滾動/IntersectionObserver）要一起做，只治一半使用者會再抓到殘留問題
- 排查瀏覽器fallback UI時，先確認fallback的DOM結構（是否保留原標籤還是整個替換），選對應的查詢方式，避免统计方法本身有系統性偏差
