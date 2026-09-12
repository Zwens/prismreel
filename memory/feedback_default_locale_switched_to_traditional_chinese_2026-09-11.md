---
name: default-locale-switched-to-traditional-chinese
description: PrismReel 2026-09-11起主要語言預設改為繁體中文(zh-Hant)，非簡體zh
metadata:
  type: feedback
---

新使用者與 unknown-locale fallback 的預設語言，從簡體中文（`zh`）改為繁體中文（`zh-Hant`）。

**改動的三個位置（缺一不可，各自獨立控制不同時機）**：
1. `frontend/src/store/settingsStore.ts` 的 zustand persist 初始值 `locale: 'zh-Hant'`（新使用者 client-side 預設）
2. `frontend/src/lib/i18n.ts` 的 `getMessages()` fallback（未知 locale 時的保底）
3. `frontend/src/app/layout.tsx` 的 `<html lang="zh-Hant">`（server-render 階段，無法讀 zustand persist，只能寫死）

**連帶發現並修正的既有 bug**：`StepHeader.tsx`/`StepPageHeader.tsx` 的 `isCJK` 判斷寫死 `useLocale() === "zh"`，只認簡體、繁體會被誤判成非 CJK 排版（字距/uppercase 邏輯跟著錯）。這個 bug 在改預設語言之前一直潛伏未被發現，因為預設是簡體、沒人特地切去繁體才會踩到。已改成 `useLocale() !== "en"`，涵蓋兩種中文 locale。

**How to apply**：以後任何「預設語言」「locale fallback」相關改動，除了上述三個明確位置，還要額外 grep `=== "zh"`（不含 `-Hant`）找出所有只認簡體判斷的隱藏邏輯一併檢查，不能只改三個入口點就當作完成。
