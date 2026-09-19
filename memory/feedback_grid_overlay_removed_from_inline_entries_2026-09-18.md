---
name: feedback_grid_overlay_removed_from_inline_entries_2026-09-18
description: 網格疊加架構第五輪收斂——移除所有內嵌上傳入口(video-gen多圖生成/首尾幀/Cast/StoryboardComposer/VideoCreator/T2ISubsection/UploadAssetModal/NewLibraryAssetDialog)的GridOverlayPicker，統一固定送原圖，網格燒錄只留「圖片生成 › 燒入網格」獨立卡片+DanceSwapWizard
metadata:
  type: feedback
---

## 這輪決策（commit `e678bce`）
[[feedback_grid_overlay_library_only_reverses_defer_burn_2026-09-18]] 之後架構又演進一次：使用者最終裁決是
「網格疊加不該綁在各生成功能的上傳入口，統一導去獨立的『圖片生成 › 燒入網格』卡片（`GridBurnCard.tsx`）」。

移除範圍（9處內嵌`GridOverlayPicker`，保留2處）：
- 移除：`MediaInput.tsx`（首尾幀i2v + 一般多圖r2v/t2i，共3處）、`UploadAssetModal.tsx`、
  `NewLibraryAssetDialog.tsx`、`Cast.tsx`、`StoryboardComposer.tsx`、`VideoCreator.tsx`、
  `T2ISubsection.tsx`（2處）
- 保留：`GridBurnCard.tsx`（獨立燒錄卡片本身）、`DanceSwapWizard.tsx`（舞蹈換裝，使用者明確排除）

移除後這些入口固定呼叫 `gridChoiceToParams('none')`，上傳一律送原圖，不再讓使用者選黑線/白線網格。
`VideoGenPage.tsx`裡引導「真人照片請至圖片生成›燒入網格再製」的提示文字（`videoGen.hint.useGrid`）
方向與新架構一致，予以保留未動。

## 🔴 教訓：使用者可見的功能變更，版本號要同步更新並版控
移除UI功能後只改了程式碼就準備push，被使用者當場糾正「下次記得版本號要更新要版控」。
`APP_VERSION`常數硬編碼在三處（`GlobalSidebar.tsx`、`SettingsPage.tsx`、`UpdateChecker.tsx`，
`UpdateChecker.tsx`註解明寫「與SettingsPage的APP_VERSION同源」但刻意不共用避免跨檔耦合），
`package.json`的version欄位反而沒在用（長期停在`0.1.0`，非權威來源）。

## How to apply
1. 之後任何**使用者可見**的功能改動（新增/移除UI、行為變更，非純內部重構）完成後，commit程式碼變更前，
   先bump這三個檔案的`APP_VERSION`常數（同一數值），單獨開一個`chore(version):`commit
2. 版本號遞增規則：功能移除/UI調整/bug修復 → patch（x.x.+1）；新增可感知功能 → minor；
   架構級改版 → major（沿用既有SemVer慣例，過去有一次從v0.2.0跳v1.5.0，不強求連號但方向要對）
3. `SettingsPage.tsx`裡`BUILD 20260613`是更早遺留的建置日期戳，本次未動（不在使用者要求範圍內），
   若之後有人決定要一併維護，需另外確認是否要改成動態日期而非硬編碼
