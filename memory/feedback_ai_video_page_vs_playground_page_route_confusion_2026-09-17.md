---
name: feedback_ai_video_page_vs_playground_page_route_confusion_2026-09-17
description: 使用者說的「AI影片頁面」對應AiVideoPage.tsx(#/ai-video)，不是PlaygroundPage.tsx(#/playground創作台)；兩者外觀高度相似容易誤改
metadata:
  type: feedback
---

修「AI影片頁面滾軸無法下滑」時，第一次改動落在 `PlaygroundPage.tsx`（`#/playground` 創作台路由），push+CI+live驗證後用JS查DOM才發現目標class（`min-w-0 min-h-0`組合）根本不存在——因為使用者說的「AI影片」實際對應完全不同的元件 `components/modules/aivideo/AiVideoPage.tsx`（`#/ai-video`路由）。

**Why**：`frontend/src/app/page.tsx` 裡 `hash === '#/ai-video'` → `AiVideoPage`；`currentView === 'playground'` → `PlaygroundPage`，兩個路由/元件完全獨立，但共用大量子元件（`ResultGallery`/`ModelSelector`/`MediaInput`/`ParameterBar`），外觀幾乎一樣。`AiVideoPage.tsx` 開頭註解自己講明是「Deliberately narrower than 創作台」的精簡版（無i2i/r2v模式），是刻意設計而非疏漏。與 [[feedback_output_data_loss_was_misdiagnosis_two_pipelines_confused_2026-09-12]] 同一類命名/路由混淆模式（那次是ComicGen vs Playground兩條產線，這次是同一產線內兩個相似頁面）。

**How to apply**：
1. 使用者說「AI影片頁面」→ 先用 `grep -n "ai-video\|'aivideo'" frontend/src/app/page.tsx` 確認對應元件，不要憑「感覺應該是Playground那套」直接動手
2. 兩頁共用元件（ResultGallery等）的修復通常只需改一處就能讓兩頁都受益；但頁面專屬容器（如`<main>`/外層`<div>`的flex/overflow設定）必須各自的檔案分別確認和修改，不能假設改一邊另一邊會自動生效
3. live驗證UI修復時，改用瀏覽器JS查`element.className`/`getComputedStyle`確認目標class真的存在於當前渲染的DOM上，比純肉眼截圖更早抓到「改錯檔案」這類問題
