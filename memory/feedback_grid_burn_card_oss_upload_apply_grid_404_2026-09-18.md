---
name: grid-burn-card-oss-upload-apply-grid-404-2026-09-18
description: GridBurnCard新增「先傳原圖、再獨立按鈕套網格」方案在OSS_ENABLE=true時對OSS URL呼叫/playground/apply-grid必404，已改回上傳前選樣式一次性燒入
metadata:
  type: feedback
---

## 事件
`GridBurnCard.tsx`（`/#/image-gen`頁「燒入網格」卡片，唯一燒圖入口，見[[feedback_grid_overlay_removed_from_inline_entries_2026-09-18]]）原本是「選圖當下用預設值`black`立即燒入」，選擇器形同虛設。第一次修復改成「先上傳原圖→再按『套用網格』按鈕」，部署後使用者實測回報「套用網格：儲存失敗，請重試 / Request failed with status code 404」。

## 根因：跟[[feedback_grid_overlay_burn_timing_deferred_to_generate_2026-09-18]]完全相同的OSS架構限制，但踩在不同檔案上
`GridBurnCard.tsx`走`/library/assets/upload`（`comic_gen/api.py`），`OSS_ENABLE=true`時回傳的是簽名OSS URL，不是本機路徑。新增的「套用網格」按鈕呼叫`playgroundApi.applyGridToMedia`→後端`/playground/apply-grid`→`resolve_local_media_path()`只認`output/`底下的本機路徑，OSS URL直接回`None`→404。
comic_gen路由（`src/apps/comic_gen/api.py`）完全沒有「對已上傳OSS圖片事後燒網格」的端點，只有上傳當下`apply_grid_overlay(data, ext, grid_size, grid_color)`一次性處理原始bytes這一種寫法（1196/3701/3783行等多處同構）。

**這代表comic_gen路由（`/library/assets/upload`等）下所有上傳入口，燒網格只能在上傳當下的同一次API呼叫內完成，事後（不論是獨立按鈕或後續步驟）一律無法對已上傳圖片補燒。** playground路由（`/playground/upload`、`/playground/apply-grid`）因為固定寫本機`output/playground/uploads/`，才有事後補燒的空間，見[[feedback_grid_overlay_burn_timing_deferred_to_generate_2026-09-18]]第16-18行的兩路徑架構差異對照。

## 修法（改回，commit待補）
`GridBurnCard.tsx`：`GridOverlayPicker`搬回上傳/資產庫選擇按鈕之前，`handleFileChange`用當下`gridChoice`轉成`gridSize`/`gridColor`直接帶入`api.uploadLibraryImage(file, gridSize, gridColor)`一次到位；移除「套用網格」按鈕與`handleApplyGrid`；`handleSave`不再嘗試對資產庫選圖路徑事後補燒（原本那段邏輯本身也會對OSS圖404，一併拔除）。
代價：選完上傳/選圖後不能再改網格樣式；資產庫選圖若選到未燒網格的舊圖，此卡片無法補燒（需回上傳入口重傳一張）。

## 🔴 教訓：既有memory已記錄過同一條架構限制，但檔名/場景不同導致第一次修復沒查到
[[feedback_grid_overlay_burn_timing_deferred_to_generate_2026-09-18]]第16-18行原文就寫著「`/upload`（comic_gen路由）...OSS_ENABLE=true時...本機無檔案可事後燒圖」，但該檔案標題與內文聚焦在`MediaInput.tsx`/`VideoCreator.tsx`，動`GridBurnCard.tsx`前用檔名/元件名搜尋memory搜不到。
**How to apply**：改任何「上傳圖片+燒網格/事後處理圖片」相關功能前，除了搜元件檔名，優先搜尾端API路由字串（如`grep -r "apply-grid\|/library/assets/upload" memory/`）或搜`OSS_ENABLE`本身，比搜元件名更能命中同一條後端架構限制的既有記錄。

## 相關
[[feedback_grid_overlay_burn_timing_deferred_to_generate_2026-09-18]] — 同一條OSS架構限制的原始發現記錄（MediaInput.tsx場景）
[[feedback_grid_overlay_removed_from_inline_entries_2026-09-18]] — GridBurnCard.tsx是目前唯一合法燒圖入口的架構決策
