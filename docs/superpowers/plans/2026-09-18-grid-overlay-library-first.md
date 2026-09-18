# 網格燒入收斂至資產庫入口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除 Playground 系列 8 個生成介面裡「本機上傳 + 延遲到生成時才燒網格」的重複邏輯，改成單一入口：資產庫頁面上傳並立即燒入網格，所有生成介面一律從資產庫選圖。

**Architecture:** `NewLibraryAssetDialog.tsx` 的「選檔案→立即呼叫 `api.uploadLibraryImage()` 燒網格→寫入資產庫」模式已經是正確模式，維持不動、僅強化為主要入口視覺。8 個生成介面各自的「本機上傳按鈕 + `GridOverlayPicker` + `gridChoice` state + submit 時燒入」邏輯全部刪除，只保留既有的「從資產庫選擇」（`AssetSourcePicker`）按鈕。`useGenerationRunner.ts` 的 `burnPendingGridOverlay` 與 `usePlaygroundStore.ts` 的 `pendingGridChoice` 整套延遲燒入狀態機隨之刪除。ComicGen 產線的 `UploadAssetModal.tsx`（`ConsistencyVault.tsx` 用）語意不同（劇本內建檔而非跨生成引用），不在本次範圍。

**Tech Stack:** Next.js 14 App Router + TypeScript + Zustand（`usePlaygroundStore`）

**Spec:** 本次無獨立 spec 文件，需求源自使用者即時回報（2026-09-18）：`/playground` 頁面網格燒入按鈕無視覺回饋，判定為「延遲到生成時才燒入」的設計與 UI 預期不符；使用者選擇改為左側欄位獨立流程。

## Global Constraints

- 所有刪除本機上傳的介面，改動前需先確認該介面是否還有「僅此模式獨有」的其他 props/邏輯依賴 `gridChoice`（如 negative prompt 注入），避免刪過頭
- `GRID_OVERLAY_NEGATIVE_PROMPT` / `GRID_OVERLAY_GUIDANCE_PROMPT` / `GRID_OVERLAY_EXCLUDE_PROMPT_SUFFIX`（`usePlaygroundStore.ts:136-154`）邏輯保留，只是觸發來源改成「選中的資產庫圖片 `hasGridOverlay` 為 true」，不再需要 `pendingGridChoice`
- 每個任務改完必須 `npm run typecheck`（或等效指令）+ 該檔案若有對應 `__tests__` 需跑過
- UI 文案一律繁體中文，不寫程式碼註解除非有非顯而易見的 WHY
- ComicGen 產線（`UploadAssetModal.tsx`、`ConsistencyVault.tsx`、`Cast.tsx` 若查證後屬 ComicGen）不在本次範圍，動手前逐一確認產線歸屬

---

## Task 0: 產線歸屬二次核實（已完成，2026-09-18）— 🔴 範圍大幅收窄

**結論（實測確認，非推測）：**

| 檔案 | import usePlaygroundStore | 已有 AssetSourcePicker | 掛載路由 | 產線歸屬 |
|---|---|---|---|---|
| `MediaInput.tsx` | ✅ | ✅ | `#/playground` | **Playground（本次範圍）** |
| `DanceSwapWizard.tsx` | ❌（但用同一套 GridOverlayPicker） | ✅ | `#/playground` 真人換裝舞蹈 | **Playground（本次範圍）** |
| `Cast.tsx` | ❌ | ❌ | `ProjectClient.tsx` | ComicGen（**排除**，同 `UploadAssetModal.tsx` 語意） |
| `StoryboardComposer.tsx` | ❌ | ❌ | `ProjectClient.tsx` | ComicGen（**排除**） |
| `T2ISubsection.tsx` | ❌ | ❌ | `StoryboardR2V.tsx` → `ProjectClient.tsx` | ComicGen（**排除**） |
| `VideoCreator.tsx` | ❌ | ❌ | `VideoGenerator.tsx` → `ProjectClient.tsx` | ComicGen（**排除**） |

**根因**：原計畫誤把「同樣 import 了 `GridOverlayPicker` 共用元件」當成「屬於同一產線」。實際上 `GridOverlayPicker`/`gridChoiceToParams` 是**跨產線共用的 UI 元件**，ComicGen 的 4 個檔案各自都是「劇本內建立角色/分鏡/場景資產」的**寫入端**（跟 `UploadAssetModal.tsx`、`NewLibraryAssetDialog.tsx` 同一種語意：選檔案→建立當下就要送出，不是「先囤een圖片庫、生成時再選」），沒有全域資產庫可引用，也不該被拔除本機上傳——拔了會讓 ComicGen 使用者完全無法上傳圖片建角色。

**本次真正範圍限縮為：`MediaInput.tsx` + `DanceSwapWizard.tsx` 兩個檔案。** Task 4-7（Cast/StoryboardComposer/T2ISubsection/VideoCreator）**全部取消**，不執行。

---

## Task 1: 刪除 Playground store 的延遲燒入狀態機

**Files:**
- Modify: `components/modules/playground/usePlaygroundStore.ts`
- Modify: `components/modules/playground/useGenerationRunner.ts`
- Test: `components/modules/playground/__tests__/storeWiring.results.spec.tsx`（跑現有測試確認未破壞）

**Interfaces:**
- Consumes: 無（此任務移除介面，不消費新介面）
- Produces: `usePlaygroundStore` 不再暴露 `pendingGridChoice` / `setPendingGridChoice`；`useGenerationRunner` 不再暴露/呼叫 `burnPendingGridOverlay`。下游任務（Task 2 起）的元件不得再引用這兩者。

- [ ] **Step 1: 確認目前有哪些呼叫點依賴這兩個介面**

```bash
grep -rn "pendingGridChoice\|setPendingGridChoice\|burnPendingGridOverlay" frontend/src --include="*.tsx" --include="*.ts"
```

記錄清單，Task 2-8 逐一清除這些呼叫點後，本任務才能真正完成刪除（先做 Task 1 的刪除會導致其他檔案編譯失敗——若 typecheck 報錯屬預期,留到對應任務修）。

- [ ] **Step 2: 在 `usePlaygroundStore.ts` 移除 `pendingGridChoice` 狀態與 setter**

移除 `usePlaygroundStore.ts:174-179` 這段（`pendingGridChoice` 定義、`setPendingGridChoice`），以及 store 實作內對應的初始值與 setter 實作。`GRID_OVERLAY_NEGATIVE_PROMPT` 等三個 prompt 常數（136-154 行）**保留**。

- [ ] **Step 3: 在 `useGenerationRunner.ts` 移除 `burnPendingGridOverlay`**

移除 `useGenerationRunner.ts:160-188` 整個 `burnPendingGridOverlay` callback 與其呼叫點；改為直接使用 `inputMediaHasGridOverlay`（此陣列保留，改由 `AssetSourcePicker.onSelect` 的 `hasGridOverlay` 參數填充，見 Task 2）。

- [ ] **Step 4: typecheck 確認影響範圍**

```bash
cd frontend && npm run typecheck
```

Expected: 報錯清單即 Task 2-8 待改檔案，全部應是「找不到 pendingGridChoice/setPendingGridChoice/burnPendingGridOverlay」相關

- [ ] **Step 5: 先不 commit**

本任務要等 Task 2-8 全部改完、typecheck 全綠才一起驗證。此步驟先跳過 commit，於 Task 8 統一驗證後才 commit 這個檔案（或在 Task 2 第一個檔案改完後就可以 commit，只要當下 typecheck 對「已改完的檔案」是綠燈——依實際情況判斷，允許本任務的 commit 延後到 Task 2 完成時一併提交）。

---

## Task 2: MediaInput.tsx 移除本機上傳與網格選擇器

**Files:**
- Modify: `components/modules/playground/MediaInput.tsx`

**Interfaces:**
- Consumes: `AssetSourcePicker`（既有元件，`onSelect: (path, hasGridOverlay?) => void`）；`usePlaygroundStore` 的 `inputMediaHasGridOverlay` setter（既有）
- Produces: `MediaInput` 不再渲染本機上傳 `<input type="file">` 與 `GridOverlayPicker`；只保留「從資產庫選擇」按鈕

- [ ] **Step 1: 移除 `renderSlot` 內的本機上傳按鈕與 file input**

`MediaInput.tsx:284-308`，刪除 `<button onClick={() => ref.current?.click()}>` 及對應的 `<input type="file" ...>`，只保留 `pickFromLibrary` 按鈕（`MediaInput.tsx:293-300`）。

- [ ] **Step 2: 移除 `firstFrame && <GridOverlayPicker .../>` 兩處渲染**

`MediaInput.tsx:322` 與 `:665`，連同 `gridChoice`/`setGridChoice` state 一併刪除。

- [ ] **Step 3: `handleAssetSelect` 確認已把 `hasGridOverlay` 寫入 store 的 `inputMediaHasGridOverlay`**

檢查現有 `handleAssetSelect(slot)` 實作，若尚未把 `AssetSourcePicker.onSelect` 的第二參數 `hasGridOverlay` 傳給 store 對應 setter，補上這段。

- [ ] **Step 4: 移除該檔案內未使用的 `handleFileChange` / upload 相關 helper**

確認刪除按鈕與 input 後，原本綁定的 `handleFileChange(slot)` 等函式若不再被任何地方引用，一併刪除，避免死代碼。

- [ ] **Step 5: typecheck + 跑該模組既有測試**

```bash
cd frontend && npm run typecheck
npx vitest run components/modules/playground/__tests__
```

Expected: PASS，無新增錯誤

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/modules/playground/MediaInput.tsx
git commit -m "refactor(playground): drop local upload and grid picker from MediaInput, library-only now"
```

---

## Task 3: DanceSwapWizard.tsx 移除本機上傳與網格選擇器

**Files:**
- Modify: `components/modules/playground/dance/DanceSwapWizard.tsx`
- Modify: `components/modules/playground/dance/useDanceSwap.ts`

**Interfaces:**
- Consumes: 同 Task 2 的 `AssetSourcePicker`
- Produces: DanceSwapWizard 三視圖/服裝參考輸入只能從資產庫選

- [ ] **Step 1: 確認 DanceSwapWizard 目前是否已有 AssetSourcePicker 入口**

依 memory 記錄（`feedback_dance_swap_pickSheet_and_seedance_negative_prompt_gap_2026-09-17.md`），"我已有三視圖"分頁已有「從素材庫選擇」按鈕。確認 AI 生成分頁與本機上傳流程是否也要拔除（AI生成分頁本身不是「上傳」，不在本次刪除範圍，只刪本機上傳按鈕）。

```bash
grep -n "localUpload\|type=\"file\"\|ref.current?.click" components/modules/playground/dance/DanceSwapWizard.tsx
```

- [ ] **Step 2: 移除本機上傳按鈕與 `GridOverlayPicker`（`DanceSwapWizard.tsx:183-203, 249-250, 339`）**

保留 AI 生成分頁邏輯不動，只刪「我已有三視圖」分頁裡的本機上傳與網格選擇器，改為引導使用者從資產庫選擇已燒網格的圖。

- [ ] **Step 3: `useDanceSwap.ts` 移除本機燒入呼叫，改用選中資產的 `has_grid_overlay` 旗標**

檢查 `useDanceSwap.ts:12` 附近的 `GridOverlaySize`/`GridOverlayColor` 使用點，若只服務於本機上傳燒入，隨 Step 2 一併移除。

- [ ] **Step 4: typecheck + 手動 live 驗證**

```bash
cd frontend && npm run typecheck
```

Live 驗證：瀏覽器打開 `/playground` → 真人換裝舞蹈 → 確認三視圖分頁只剩「從資產庫選擇」，不再有本機上傳按鈕與網格選擇器

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/modules/playground/dance/DanceSwapWizard.tsx frontend/src/components/modules/playground/dance/useDanceSwap.ts
git commit -m "refactor(dance-swap): drop local upload and grid picker, library-only reference images"
```

---

## Task 4-7: 已取消（2026-09-18 Task 0 核實後撤銷）

Cast.tsx / StoryboardComposer.tsx / T2ISubsection.tsx / VideoCreator.tsx 經核實均屬 ComicGen 產線（掛載於 `ProjectClient.tsx` 下），非 Playground 產線，且均無 `AssetSourcePicker` 可用、無全域資產庫可引用。這 4 個檔案的本機上傳是必要功能，**不執行任何改動**。

---

## Task 8: 收尾 — 刪除共用元件與死代碼，跑完整驗證

**Files:**
- Modify: `components/modules/playground/usePlaygroundStore.ts`（若 Task 1 Step 5 延後的 commit）
- Modify: `components/modules/playground/useGenerationRunner.ts`
- Review: `components/shared/GridOverlayPicker.tsx`（若 8 個生成介面都不再用，僅 `NewLibraryAssetDialog.tsx` 使用，簡化 export 或保留現狀均可，不強制刪除元件本身）
- Review: `lib/api.ts:1825`（`/playground/apply-grid` 端點若無呼叫者則確認是否還有其他用途，勿刪除後端路由——後端不在本次範圍）

**Interfaces:**
- Consumes: Task 2（MediaInput.tsx）+ Task 3（DanceSwapWizard.tsx）的改動結果（Task 4-7 已取消，不在依賴範圍）
- Produces: 全專案 typecheck 綠燈、無死代碼引用

- [ ] **Step 1: 全域 grep 確認沒有殘留引用**

```bash
grep -rn "pendingGridChoice\|setPendingGridChoice\|burnPendingGridOverlay" frontend/src --include="*.tsx" --include="*.ts"
```

Expected: 無結果（若 Task 1 Step 5 尚未 commit，此時一併 commit）

- [ ] **Step 2: 確認 `GridOverlayPicker` 僅被 `NewLibraryAssetDialog.tsx` 引用**

```bash
grep -rln "GridOverlayPicker" frontend/src --include="*.tsx"
```

Expected: 只剩 `components/library/NewLibraryAssetDialog.tsx` 與元件自身檔案

- [ ] **Step 3: 全專案 typecheck + lint**

```bash
cd frontend && npm run typecheck && npm run lint
```

Expected: 0 errors

- [ ] **Step 4: 跑全部既有前端測試**

```bash
cd frontend && npx vitest run
```

Expected: 全部 PASS（若既有測試斷言 `GridOverlayPicker` 出現在已刪除的元件內，需同步更新該測試 — 這屬於本任務範圍內的必要修正，非「順手改」）

- [ ] **Step 5: 依 CLAUDE.md §2 驗收等級 L3，push 後等 GitLab CI success，再等 60 秒，再 live 驗證**

```bash
git push origin main
```

CI success 後：

```bash
sleep 60
```

Live 驗證（瀏覽器實測，不可用 curl 代替，因為是 UI 互動變更）：
1. 打開 `https://prismreel.soulo-ai.com/#/playground` → 確認 MediaInput 只剩「從資產庫選擇」
2. 打開資產庫頁面 → 確認「新增資產」流程選檔案後立即燒網格（看得到燒網格後的縮圖）
3. 打開真人換裝舞蹈 → 確認三視圖分頁只剩「從資產庫選擇」
4. 打開任一 ComicGen 專案（Cast / StoryboardComposer / T2ISubsection 任一頁面）確認**本機上傳功能未受影響、仍正常**（本次未改動這幾個檔案，此步驟是回歸驗證，確認 Task 1 對 store 的改動沒有意外波及不相關產線）

- [ ] **Step 6: 閘門6記憶更新**

依 CLAUDE.md §2 閘門6三步驟，寫入 `AI 短片系統 Prismreel/memory/` 新 feedback 檔記錄本次架構收斂的根因（延遲燒入時機與UI無視覺回饋的落差）與最終方案，並更新 `MEMORY.md` 索引一行；append 當日 daily-log。

---

## Self-Review 檢查結果

1. **Spec 覆蓋**：使用者兩點決策（左側欄位=資產庫頁面新增入口；生成介面全改成只能選庫）均對應 Task 2-8；資產庫端因已符合正確模式，Task 8 僅做收尾確認，未新增多餘任務。
2. **佔位符掃描**：Task 4-7 因等待 Task 0 的產線歸屬結論，Step 內容部分較簡略（未逐行列出行號改動細節）——這是刻意設計，因 Task 0 的輸出會決定這些檔案的確切改法，執行者需先跑 Task 0 才能精確定位；已提供 grep 指令與既有範例檔案（Task 2/3）作為施工樣板，非空泛描述。
3. **型別一致性**：全程沿用既有 `AssetSourcePicker` 的 `onSelect: (path: string, hasGridOverlay?: boolean) => void` 簽名，未新增介面，無不一致風險。
