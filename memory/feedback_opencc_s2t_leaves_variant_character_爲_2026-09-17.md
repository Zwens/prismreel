---
name: opencc-s2t-leaves-variant-character-爲
description: opencc s2t profile轉簡體為繁體後會殘留「爲」異體字，需額外正規化為台灣慣用「為」
metadata:
  type: project
---

程式碼註解簡體字清理第三輪（前端`src`全部53個乾淨檔案，排除當時claude-wmzic-5f正在改的`useDanceSwap.ts`/`useGenerationRunner.ts`/`usePlaygroundStore.ts`/`lib/api.ts`四個檔案）用`opencc.OpenCC('s2t')`轉換後，跑`git diff`複查發現26處簡體「为」被轉成異體字「爲」而非台灣慣用的「為」（如「歸類爲」），s2t profile只做嚴格繁簡對應不做地區用字正規化。

**Why**：opencc的`s2t`（Simplified to Traditional）只保證繁簡轉換正確，不等於「轉成台灣教育部標準用字」；「爲/為」是傳統繁體圈常見異體字並存現象，`s2t`不會主動選字，需另外`s2twp`（Simplified to Traditional, with Taiwan idiom/phrases）或轉完後手動re.sub正規化。

**How to apply**：往後任何簡體字批次清理任務，轉換後除了跑`node --check`/typecheck驗證語法完整，還要額外`grep -c '爲'`複查，命中就補一次全文字串替換`爲`→`為`（純字元替換不影響語法，無需重新typecheck）。下次可直接改用`opencc.OpenCC('s2twp')`從源頭避免此問題，省去二次修正步驟。

本輪commit `2b11692`已完成53個檔案的清理+異體字修正，已push並typecheck+lint交叉驗證無新增錯誤（lint既有664條`no-explicit-any`類錯誤與本次改動無關，stash比對確認）。
