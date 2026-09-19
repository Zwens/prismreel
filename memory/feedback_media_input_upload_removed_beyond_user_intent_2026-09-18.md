---
name: feedback_media_input_upload_removed_beyond_user_intent_2026-09-18
description: commit f654d25「MediaInput改回資產庫單一入口」誤把本地拖檔上傳整個拿掉，使用者原意只針對網格燒入時機/真人臉部追蹤情境（✅2026-09-18已還原）
metadata:
  type: feedback
---

## ✅ 2026-09-18 已還原
接手session動手前先查git log/plan文件，發現`f654d25`其實有完整計畫文件+commit message
明確寫「Removed local upload entirely」，跟本檔案原始交接說法（peer session轉述「意外綁在一起」）
不一致，故用AskUserQuestion向使用者核實，確認「就是要加回本地上傳」後才動手（避免peer交接
默默推翻或誤傳使用者裁決，見workspace `feedback_peer_handoff_must_not_silently_reverse_users_own_decision`）。
已以`5835289`（f654d25前一版，含完整本地上傳UI）為藍本，加回`MediaInput.tsx`的本地拖檔/選檔上傳，
但網格燒入邏輯**不**用`5835289`的延遲燒入機制（那個已被使用者放棄），改用上傳當下用`GridOverlayPicker`
選好的值立即燒入（`gridChoiceToParams`+`playgroundApi.uploadMedia(file, gridSize, gridColor)`）。
本地上傳與資產庫選取兩條路徑並存。`npm run typecheck`綠燈、既有`MediaInput.assetSource.spec.tsx`
測試綠燈（`AssetSourcePicker.spec.tsx`4個既有失敗與本次改動無關，改動前後行為一致）。
瀏覽器視覺驗收因誤觸「環境配置」全域`.env`覆寫事故中止（見
[[feedback_env_config_dialog_writes_global_env_not_per_account_2026-09-18]]），未完成截圖驗收，
僅完成靜態程式碼審查+typecheck+單元測試三層驗證。

## 使用者原意 vs 實際改動範圍

commit `f654d25`（見 [[feedback_grid_overlay_library_only_reverses_defer_burn_2026-09-18]]）把
`MediaInput.tsx` 改成「只能從資產庫選圖」單一入口，撤銷了同日稍早
`5835289` 的延遲燒入設計。

2026-09-18 稍晚，開發「多鏡頭影片工作流」時發現 `MediaInput`/`AssetSourcePicker`
現在完全沒有本地拖檔上傳入口，一度誤判為「舊回歸bug」要交給新session修。
使用者立刻更正：**他當時的意思只是「真人臉部追蹤場景需要先網格燒入，非真人
影片不受這個問題影響」，從未要求移除本地拖檔上傳功能本身。**

`f654d25` 把「網格燒入時機的取捨」跟「上傳入口只能是資產庫」兩件事綁在一起
改了，範圍超出使用者實際同意的範圍。

## Why
使用者需要能夠現場上傳一張全新的圖片（尤其在多鏡頭工作流的 ShotCard 裡，
不該強迫使用者先跳去 Library 頁面上傳再回來選）。網格燒入只是「真人臉部
追蹤」情境下的建議動作，不是所有上傳都必須先過網格燒入流程。

## How to apply
下一個處理此問題的 session（或本session稍後）需要：
1. 在 `MediaInput.tsx` 加回本地拖檔/選檔上傳入口，呼叫既有
   `playgroundApi.uploadMedia`（圖片，可選 grid_size 供真人場景燒入）/
   `uploadVideo`（影片）
2. 上傳與資產庫選取應並存，不是互斥——使用者可以「本地上傳新圖」也可以
   「從資產庫挑舊圖」，兩條路徑都要保留
3. 網格燒入選項（grid_size/grid_color）只在上傳圖片這條路徑上出現，讓
   使用者依「是否是真人」自行決定要不要燒網格，不要強制
4. 新的「多鏡頭影片工作流」（[[project_video_workflow_multi_shot_2026-09-18]]）
   的 ShotCard 媒體輸入區塊應該與修好後的 MediaInput 走同一套上傳+選取雙軌
   模式，不要各自兩套不一致的邏輯
