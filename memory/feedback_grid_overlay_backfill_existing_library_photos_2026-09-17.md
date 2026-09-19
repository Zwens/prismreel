---
name: grid-overlay-backfill-existing-library-photos-2026-09-17
description: 素材庫既有照片補套用網格疊加backfill——實測資料量遠小於理論資料模型複雜度，三代legacy欄位全空
metadata:
  type: feedback
---

✅ 2026-09-17 已完成（跨session交接任務，claude-wmzic-0f → claude-wmzic-0d）。

**背景**：照片上傳網格疊加功能（[[feedback_grid_overlay_upload_feature_2026-09-17]]，commit `d89c0f8`）只對新上傳生效，使用者要求既有素材庫照片統一補套用5×5網格，不分來源。

**理論複雜度 vs 實際資料量落差**：`Character` model 圖片欄位有三代並存——legacy單一URL（`full_body_image_url`等）、中間版`*_asset.variants[]`、目前版`reference_sheet.image_variants[]`（見`src/apps/comic_gen/models.py`）。交接檔只提到第三代，遺漏前兩代。但實查VPS `library_assets.json`（唯讀`docker exec cat`）發現：前兩代欄位在目前資料裡**全部是空值**，實際只有2個character各1張圖（走`reference_sheet.image_variants[]`）+ 1個prop（純video無圖）+ 0個scene。理論範圍與實際待處理量可以差很多，**backfill前務必先實查production資料量，不能只憑資料模型定義推估工作量**。

**額外簡化**：兩張圖的URL都是容器內本機路徑（`output/assets/character/...`），不是OSS簽名URL，因此完全不需要交接檔擔心的「OSS只有上傳沒下載封裝」問題，改用`docker cp`直接取出/寫回容器即可，比OSS下載/重新上傳簡單很多。

**執行方式**：
1. `docker exec ... cp library_assets.json library_assets.json.bak.<timestamp>`（**docker exec不會展開`&&`，需包一層`sh -c '...'`**，直接`docker exec container cmd1 && cmd2`會靜默只執行第一段）
2. `docker cp` 取出兩張圖 → 本機 `apply_grid_overlay(bytes, "png", 5)` → `docker cp` 寫回原路徑（同路徑覆蓋，因為URL不變，不需要改JSON任何欄位）
3. 因為只覆蓋圖片檔案內容、未改`library_assets.json`本身，**不需要`docker restart`**（重啟只在改JSON結構時才需要，避免in-memory pipeline singleton下次autosave覆寫）

**驗證方法**：SHA256比對本機輸出與容器內檔案逐位元組一致 → 瀏覽器登入素材庫頁面，找到頁面實際渲染的`<img>`元素（DOM查`document.querySelectorAll('img')`拿真實`src`，不要自己猜URL路徑——直接fetch猜測路徑`/output/...`得到401，實際前端用的是`/files/...`路徑）→ canvas `getImageData`在網格線理論座標採樣確認黑色像素存在，比純肉眼截圖判斷1px網格線可靠（縮放截圖下1px線常被抗鋸齒吃掉，肉眼看不出來不代表沒有）

**How to apply**：
1. 任何「backfill既有資料」任務，動工前先唯讀盤點production實際資料量，不要只讀程式碼/資料模型定義去估工作量，範圍可能被高估或低估
2. `docker exec`需要shell特性（`&&`/管線/變數展開）時必須`sh -c`包起來
3. 驗證疊加/浮水印類細節（1px線、浮水印等）優先用像素採樣（canvas/PIL getpixel），不要只信肉眼截圖
