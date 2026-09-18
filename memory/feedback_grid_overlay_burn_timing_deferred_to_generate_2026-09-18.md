---
name: grid-overlay-burn-timing-deferred-to-generate-2026-09-18
description: 網格疊加燒圖時機根因修復——選圖當下立即燒圖導致UI改網格選項不生效，改為送出生成時才燒圖（⚠️此設計已於同日被撤銷，見下方更新）
metadata:
  type: feedback
---

## 🔴🔴 已撤銷（同日 2026-09-18 稍晚）
本檔記錄的「延遲到生成時才燒入」設計，導致使用者在`/playground`實測時回報「網格燒入按鈕沒反應」（因為延遲燒入沒有任何視覺回饋）。已改回「只能從資產庫選已燒好的圖，選了就是最終結果」，見 [[feedback_grid_overlay_library_only_reverses_defer_burn_2026-09-18]]。本檔的根因分析（「切換網格樣式對已選圖不生效」）與驗證方法論仍有參考價值予以保留，但**此檔記錄的`pendingGridChoice`/`burnPendingGridOverlay`機制本身已從`MediaInput.tsx`/`usePlaygroundStore.ts`/`useGenerationRunner.ts`移除（commit `f654d25`），不要再依此檔案內容判斷目前程式碼現況**。

## 根因（跟先前三輪UI/prompt/negative_prompt修復完全不同層次）
使用者回報「AI影片頁圖生影片模式，跟之前舞蹈那邊一樣反了」，第一直覺誤判為UI排列順序問題（[[feedback_grid_overlay_three_defects_ai_gen_dance_negative_prompt_2026-09-17]]系列都是這個層次）。用 AskUserQuestion 核實後，使用者確認真正問題是**燒圖時機**：`MediaInput.tsx`/`VideoCreator.tsx` 的上傳流程是「選圖=立即呼叫上傳API並用當下`gridChoice`燒圖」，網格是`gridSize>0`時後端`apply_grid_overlay`永久燒入像素，之後在UI上再切換網格選項完全不會回頭套用到已選的圖——UI位置對不對根本不是重點，选图当下网格选项的值才是唯一生效的值。

**教訓**：使用者說「反了」時不要只看UI渲染順序，要往下查資料流「這個值在哪個時間點被消費」。先動手改了兩處純UI搬移（`VideoCreator.tsx`已push的commit`23bf601`、`MediaInput.tsx`後來revert），確認是誤判方向後才用AskUserQuestion核實，避免了在錯誤前提上繼續擴大改動。

## 兩條上傳路徑的架構差異（動手前先查證，不能假設一致）
- `MediaInput.tsx`（Playground用）→ `/playground/upload`：永遠寫本機`output/playground/uploads/`，不受OSS影響，可以「先傳原圖→送出前對本機路徑事後apply-grid」
- `VideoCreator.tsx`（漫畫生成Motion步驟用，`/#/ai-video`頁面**不會**用到這個元件，見下方「相關」）→ `/upload`（comic_gen路由）：OSS_ENABLE=true時檔案上傳後直接送OSS，回傳OSS URL，本機無檔案可事後燒圖，必須改成「選圖只做本地預覽blob，送出生成當下才真正呼叫上傳API」才能修對，改動範圍明顯更大，本次未處理

## 修法（僅MediaInput.tsx路徑，即`/#/ai-video`頁面 AiVideoPage.tsx 實際使用的元件）
commit`5835289`：
1. `usePlaygroundStore.ts`新增`pendingGridChoice`+`setPendingGridChoice`，取代原本散落在`MediaInput.tsx`/`FirstLastFrameInput`兩個元件內各自獨立的local `gridChoice` state（送出生成的`useGenerationRunner.ts`是不同元件，local state互相看不到，必須提升到共用store）
2. `MediaInput.tsx`三處上傳入口（`FirstLastFrameInput.uploadTo`、主元件`handleFiles`）全部改成固定`gridSize=0`上傳原圖，`inputMediaHasGridOverlay`固定寫`false`
3. `useGenerationRunner.ts`新增`burnPendingGridOverlay()`：`handleGenerate`执行時，若`pendingGridChoice!=='none'`，對每個`inputMedia[i]`且`!inputMediaHasGridOverlay[i]`且非官方角色ref/非http(s)/blob/data URL（素材庫已燒過網格的圖片會標記`true`，不重複燒），呼叫既有`POST /playground/apply-grid`原地燒圖，回填`inputMedia`+`inputMediaHasGridOverlay`後才建立請求；`GenerationRunner.generate`介面型別同步改成`() => Promise<void>`
4. `GridOverlayPicker`三處渲染位置從「圖片上傳區之前」搬到「已選圖片之後」（`FirstLastFrameInput`空狀態完全不渲染，`hasMedia`才顯示）

## Live驗證方法論
用真實付費API生成驗證（Seedance 2.5 I2V，$1.156）：素材庫選圖→縮圖仍是原圖確認未提前燒圖→切換「6×6網格(黑線)」→查後端log確認`POST /playground/apply-grid`是在按下生成鈕那一刻才被呼叫（不是選圖當下）→`docker cp`把燒圖後的檔案抓下來本機Read工具肉眼確認網格線已燒入→截圖確認「生成結果排除網格線」checkbox自動勾選（`inputMediaHasGridOverlay`正確變true，下游GRID_OVERLAY_GUIDANCE_PROMPT/negative prompt邏輯正常銜接）。

## 已知殘留缺口（下次接手需處理）
1. `VideoCreator.tsx`（漫畫生成Motion步驟）**同樣的燒圖時機問題完全未修**，commit`23bf601`只做了UI位置搬移（無害但未解決根因）；因為`/upload`走OSS，修法必須是「選圖只本地預覽，送出時才真正上傳」，架構改動比MediaInput.tsx路徑更大，需要處理`selectedImages`/`uploadingPaths`/R2V `castSlots`等多個state
2. 本次僅驗證「素材庫選擇」入口；「本地上傳」（`本地上傳`按鈕/拖曳）入口程式碼邏輯一致（同樣改用`gridSize=0`+送出前燒圖），但受限於瀏覽器自動化工具無法選本機任意檔案，未做真實生成驗證，僅程式碼審查確認

## 相關
[[feedback_ai_video_page_vs_playground_page_route_confusion_2026-09-17]] — `/#/ai-video`對應`AiVideoPage.tsx`+`MediaInput.tsx`，非`VideoCreator.tsx`，兩者外觀相似但完全不同元件/不同上傳API，本次一開始也踩到這個混淆，改錯`VideoCreator.tsx`才發現使用者截圖的頁面根本不會用到它
[[feedback_grid_overlay_three_defects_ai_gen_dance_negative_prompt_2026-09-17]] — 先前三輪修復皆處理「網格有沒有生效/prompt有沒有注入」，本次是第一次處理「燒圖時機」這個更底層的問題
