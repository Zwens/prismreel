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

## 🔴🔴 第二輪重演：ModelArk搜尋框本身會卡死，用它抓資料前必先驗證"changed"而非只看alt/完成度（2026-09-15同日）

上面「30筆100%命中」的驗證方法本身有致命缺陷：用`setReactInputValue`連續快速切換搜尋框輸入值，第2筆之後畫面完全卡死在第1筆結果（"Benin 22-year-old male Real Estate Agent"）不再刷新，但`img.alt`屬性殘留值恰好每次看起來都不同（因為DOM節點沒被替換，alt還是舊的），肉眼截圖confirm時只看了第1、2張就誤判為「正常運作」。結果：30個不同asset_id全部下載成同一張圖（MD5雜湊完全一致），已commit `398dcca`+`d8758f5`上線，使用者實測發現「一排長得一模一樣的人」才揪出。

**判斷方法**：不能只憑`alt`文字或單次截圖判斷搜尋結果是否真的刷新，必須用`fetch(url)`比對SHA-256雜湊，或檢查完整`img.src`（含query string簽名）是否真的變化。

**修復手法（已驗證可靠）**：放棄搜尋框，改用React fiber直讀 `item.SID`（對應official.json的`group_id`，非`asset_id`）+ 在預設列表滾動，不依賴搜尋功能。30筆全部一次滾動命中，且29張雜湊互不相同（第30張`xc8v4`本來就是對的沒被污染）。commit `c5db137`已修正並live驗證雜湊一致。

**已知殘留待辦（已結案，見下方2026-09-15續查結論）**：另外3對（6筆，`asset-20260225014832-bdcj7`/`014826-lr75n`、`014910-4hq8j`/`014919-k4dcd`、`015321-rcxrz`/`015258-npckt`）縮圖雜湊也重複，屬於更早批次（120原有或早期補的），暫不確定是ModelArk庫裡真實的「雙胞胎」角色還是同款抓取錯誤，已滾動300+張追查未果，使用者裁決今日先結案，下次用同一套「React fiber滾動」手法接續排查。

## 🔴 續查結論（同日另一session）：3對6筆確認是ModelArk資料庫本身重複記錄，非抓取錯誤

**排查手法**：滾動列表本身在120+筆後遇到虛擬列表瓶頸（固定卡在同一批119筆不再新增，怀疑是渲染節流而非資料上限），改回用搜尋框單次查詢（非連續切換，避開已知卡死陷阱）+ 按Enter確認觸發 + 等待圖片完全載入後才用React fiber讀`item.SID`比對。

**驗證結果（3對全部同一結論）**：
- `group-20260225014919-l6k7s` vs `group-20260225014910-hfk69`（China 62-year-old female Farmer）→ 搜尋"China 62 female Farmer"皆命中，兩張圖SHA-256雜湊完全一致（size 1440652 bytes）
- `group-20260225014832-h2lvw` vs `group-20260225014826-rzwdt`（China 75-year-old female Fruit Farmer）→ 兩張圖SHA-256雜湊完全一致（size 1674020 bytes）
- `group-20260225015321-ll9z7` vs `group-20260225015258-gxq2x`（Japan 28-year-old male Model）→ 搜尋"Japan 28 male Model"皆命中，兩張圖SHA-256雜湊完全一致（size 1741771 bytes）

**結論**：3對6筆的group_id/asset_id在ModelArk平台上是兩筆獨立資料庫記錄（都能被搜尋獨立命中），但**平台自己對這兩筆記錄提供的原始圖片檔案本身就相同**——不是雙胞胎角色（不存在第二張不同臉的圖），也不是我方抓取/下載流程出錯。本機480張縮圖對這3對的呈現是忠實反映源頭資料，**不需要也無法修復**（沒有「正確的第二張圖」可抓）。此殘留待辦到此結案，不再需要後續排查。

**How to apply**：往後遇到「official.json兩筆不同asset_id但biography/title完全相同」的情況，先假設是ModelArk資料庫本身的重複記錄，用搜尋框單次查詢+fetch雜湊比對確認，不要預設是己方抓取流程的bug去找不存在的「正確圖」。
