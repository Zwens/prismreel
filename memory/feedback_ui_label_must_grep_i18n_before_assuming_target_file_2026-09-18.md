---
name: feedback_ui_label_must_grep_i18n_before_assuming_target_file_2026-09-18
description: 使用者說「多圖生成/影生影沒有上傳」，未先grep i18n key定位UI標籤對應檔案就假設是storyboard-r2v分鏡工作流，改錯檔案並push上線；正確目標其實是Playground的MediaInput.tsx
metadata:
  type: feedback
---

## 事故經過
使用者原話「多圖生成為什麼還是沒有辦法自己上傳圖片」。當下憑「R2V=多參考圖生成」的概念聯想，
直接查了 `storyboard-r2v/ShotCard.tsx`（既有分鏡工作流），發現它只能透過資產庫chip引用素材、
無本地上傳，於是設計「上傳建臨時prop資產」方案並實作、commit、push上線。

使用者驗收後回報「都沒有看到 input 上傳的地方 [多圖生成] & [影生影]」——這兩個方括號字面正是
i18n key `videoTab.r2v`/`videoTab.v2v` 的值，對應的是 **Playground 的 `VideoGenPage`/
`MediaInput.tsx`**（分頁標籤機制），跟 `storyboard-r2v/ShotCard.tsx`完全是不同介面/不同資料模型。
兩邊命名恰好都叫「R2V」造成誤判。

## 🔴 核心教訓：使用者引用UI上的具體文字/方括號標籤時，先grep該字串找i18n key，不要憑術語聯想
`grep "多圖生成\|影生影"` messages/*.json 一秒就能鎖定 `videoTab.r2v`/`videoTab.v2v`，直接指向
`MediaInput.tsx`/`VideoGenPage.tsx`。若在動手前先做這步，能省下一整輪「改錯檔案+push+等使用者
驗收失敗回報」的來回成本。

## Why
這個專案存在多套「看起來像同一個概念」的並行系統（storyboard-r2v分鏡工作流 vs Playground單次
生成頁），且兩邊都用「R2V」這個技術詞彙自稱。純技術術語聯想在多入口/多產線的專案裡不可靠，
使用者的原話（尤其帶引號/方括號的具體UI文字）比工程師自己的概念分類更準確。

## How to apply
1. 使用者描述「某功能沒有/壞了」且引用了具體的按鈕文字、分頁名稱、方括號標籤 → 動手前第一步是
   `grep` 該字串到 `frontend/messages/*.json`，用 i18n key 反查對應元件，而不是靠功能名稱聯想
2. 多套並行系統/產線共用相同技術詞彙（如本案「R2V」）時，永遠不能假設「聽起來對」就是同一個
3. 找到候選檔案後，若該檔案本身已存在完整的上傳邏輯（如本案第一輪讀`MediaInput.tsx`時已見過
   `handleFiles`/`fileInput`完整實作），要更謹慎意識到「這可能不是我要找的壞掉的那個」，而非
   直接跳去查另一個看起來也合理的檔案

## 意外收穫：改錯地方的過程中發現真正的技術債
驗證另一session未提交的`MediaInput.tsx`本地上傳還原時，`eslint`揪出`react-hooks/rules-of-hooks`
error：新加的`useCallback`（拖曳三件事件）宣告在i2v模式的條件式`early return`之後。同一次mount
若切換過mode（i2v↔r2v/v2v/t2i），React偵測到hooks數量不一致直接報錯，導致整個媒體輸入區塊
渲染失敗消失——這正是使用者回報「看不到上傳入口」的真正根因之一，比「檔案沒commit」更關鍵。
已改成一般函式（這些handler未被記憶化子元件使用，`useCallback`本來就沒有實質效益）。
**教訓延伸**：驗證他人未提交的修復時，不能只看memory記錄的「typecheck綠燈」就假設沒問題——
memory本身就寫了「瀏覽器視覺驗收因故中止」，代表這條防線沒跑過，`eslint`（含react-hooks
plugin）是比typecheck更能抓到這類條件式hooks錯誤的工具，逐層驗證不能因為前一層綠燈就跳過。

## 相關
[[feedback_media_input_upload_removed_beyond_user_intent_2026-09-18]] — 本次驗證的未提交還原內容
