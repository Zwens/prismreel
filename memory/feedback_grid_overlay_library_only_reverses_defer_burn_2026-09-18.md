---
name: grid-overlay-library-only-reverses-defer-burn-2026-09-18
description: MediaInput.tsx改回「只能從資產庫選圖」單一入口，撤銷同日稍早的延遲燒入設計；動手前未查git log差點推翻自己剛做的修復
metadata:
  type: feedback
---

## 事件脈絡（同一天兩次方向相反的修復，且是同一個session做的）
1. `5835289`（2026-09-18 10:23，[[feedback_grid_overlay_burn_timing_deferred_to_generate_2026-09-18]]）：把「選圖當下立即燒入」改成「延遲到按生成時才燒入」，解決「選圖後切換網格樣式，已選圖片不會重新套用」的問題，有真實付費API驗證
2. 使用者隨後在`/playground`實測，回報「網格燒入按鈕沒有產生燒入圖片」——這其實是(1)的**預期行為**（燒入被延遲了，UI卻沒有任何提示「這是延遲的」），被誤認為新bug
3. 本次修復：直接聽取使用者「拔掉延遲燒入，改資產庫單一入口」的方向，動手前完全沒查git log，過程中意外`git stash`才發現`5835289`是稍早的自己做的

## 🔴 核心教訓：改別人「昨天/今天稍早」的commit前，必須先查那次commit的理由
本次差點犯的錯：直接把`pendingGridChoice`/`burnPendingGridOverlay`當成「舊架構遺留問題」整個拆除，若沒有中途`git stash`意外發現`5835289`，會在不知情的狀況下重新引入(1)已經修掉的bug（「切換網格樣式對已選圖不生效」）。
**動手拆除/反轉任何機制前，先`git log --oneline -20 -- <要改的檔案>`看最近改動歷史與commit message，尤其當使用者的新回報「聽起來很像在反駁」某個最近才做的設計時。**

## 這次的trade-off（已用AskUserQuestion取得使用者明確同意）
新架構：網格燒入只在「資產庫上傳當下」發生一次，選了就是最終結果；想換樣式=重新上傳一張新資產，不能對已選圖片事後切換。
用「選完即所見即所得」的確定性，換掉「事後可調整網格樣式」的彈性。使用者知情且接受這個取捨。

## 範圍查證方法論（原計畫誤判8個檔案，實際只改1個）
最初以為`Cast.tsx`/`StoryboardComposer.tsx`/`T2ISubsection.tsx`/`VideoCreator.tsx`跟`MediaInput.tsx`同屬Playground產線（都import了`GridOverlayPicker`共用元件），查證後發現：
- `GridOverlayPicker`是跨產線共用UI元件，不代表同一產線
- 那4個檔案實際掛在`ProjectClient.tsx`下，屬ComicGen漫畫劇本產線（角色/分鏡/場景建置），不是Playground
- 判準：`grep "usePlaygroundStore"` + `grep "AssetSourcePicker"` 兩者皆無 → 該檔案沒有全域資產庫可引用，本機上傳是必要功能，不該拔
- `DanceSwapWizard.tsx`也在原計畫範圍內，查證後發現它的網格燒入本來就是「選了就送出」（AI生成分頁）或「明確按鈕觸發」（GridBurnBar），沒有延遲燒入問題，不需要改

**教訓**：「兩個檔案import了同一個共用元件」≠「屬於同一產線、該套用同一種改法」，動手前用`usePlaygroundStore`/`AssetSourcePicker`這類產線專屬依賴做判準，比看共用元件更準。

## 部署驗證踩坑：瀏覽器快取讓first-pass live驗證產生假陰性
`docker inspect`確認容器已重啟（02:25 UTC）、grep build產物確認字串存在後，第一次瀏覽器截圖仍看到舊版「本地上傳」按鈕，一度以為部署沒生效。改用`location.reload(true)`強制重新整理後才看到正確的新版UI。
**教訓**：nginx靜態檔沒有CDN層快取，但瀏覽器自己的HTTP快取仍可能讓同一個Chrome tab在容器重啟後看到舊版，live驗證前先強制reload，不要只看一次截圖就下結論。

## 相關
[[feedback_grid_overlay_burn_timing_deferred_to_generate_2026-09-18]] — 這次撤銷的前一輪修復，含完整根因與驗證方法
[[feedback_ai_video_page_vs_playground_page_route_confusion_2026-09-17]] — 同樣是MediaInput.tsx相關的路由/元件歸屬混淆案例
