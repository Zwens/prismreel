---
name: nav-reorg-video-image-gen-split
description: 左側導覽拆分影片生成/圖片生成兩入口，三session（0d/c5/1b）分工完成
metadata:
  type: project
---

✅ 2026-09-18 已完成：左側導覽從6項（workspace/library/aivideo/playground/history/settings）改為5項（漫畫生成/素材庫/影片生成/圖片生成/生成歷史/設定），`#/ai-video`路由與`AiVideoPage.tsx`整個廢棄併入「影片生成」。commit `9fa3884`，pipeline #45782已通過，live驗證確認全部功能正常。

**架構決策**：VideoGenPage.tsx（5個tab：t2v/i2v/r2v/v2v/dance，直接開compose不經卡片選單）與ImageGenPage.tsx（3張卡片：t2i/i2i/燒入網格）都各自建立獨立的`PlaygroundStoreProvider` store實例，不共用模組級單例——跟原本`AiVideoPage`的隔離模式一致，避免兩個入口互相覆寫mode/prompt/inputMedia。

**測試遷移教訓**：既有`storeWiring.surfaces.spec.tsx`/`emptyMode.spec.tsx`原本假設`PlaygroundPage`走全域單例`playgroundStore`，可以直接`playgroundStore.setState()`後渲染頁面斷言。改成獨立store後，這招失效——測試需要改成把`ImageGenWorkspace`/`VideoGenWorkspace`（内部函式改具名export）包在測試自建的`PlaygroundStoreProvider`裡，才能注入`maxConcurrent`/`activeGenerationIds`這類無UI對應的內部狀態。

**多人協作教訓**：與peer session（c5）同時建立`GridBurnCard.tsx`佔位版 vs 完整版時發生一次互相覆蓋，事後補協議「同一檔案只由認領方動」化解；後續i18n key命名沒有事先完全對齊（`imageGen.gridBurn.*`由c5定案，我原先猜測的`imageModeCard.gridBurn.*`需要重新對齊），下次分工應在動工前先把介面/key命名一次講清楚，而非各自先猜測再對齊。

**vitest雙config發現**：專案有`vitest.config.mts`(node環境，只收`src/__tests__/**`)和`vitest.ui.config.mts`(happy-dom環境，收`src/components/**/*.spec.tsx`)兩份設定，`npm test`只跑前者，`npm run test:ui`才會跑到元件級DOM測試；本次改動涉及的`storeWiring.*`/`emptyMode`/`GlobalSidebar`測試都要用`test:ui`才能驗證，純`npm test`會誤判「跑不到」。

**既有技術債（非本次引入）**：`AssetSourcePicker.spec.tsx`4個測試斷言`onSelect`只帶單一參數，但實際呼叫多帶了一個`undefined`第二參數；用`git stash`驗證過跟本次改動無關，commit `c08d8f2`就已存在，未修復。

**✅ 追加修復（同日，commit `b41b99c0`，pipeline #45784）**：VideoGenPage.tsx的tab文字最初圖省事直接沿用既有`playground.mode.*` key（`mode.t2v`="文生"等），沒注意到這個key同時被`ModeSelector.tsx`的results階段窄版pill共用——那邊為了塞進小空間才設計成簡稱，不是給tab用的完整文字。使用者驗收時指出文字不對（要「文字生成/首尾幀/多圖生成/編輯影片/動態捕捉生成」），改成新增專屬`playground.videoTab.*` key解決。**教訓：新UI元件若圖方便直接複用既有i18n key前，先grep該key的其他呼叫點，確認是否為「因應別處空間限制而簡化過」的文字，不能假設同一語意的key在不同UI位置都適用同一版本的文字。**
