---
name: grid-overlay-upload-feature-2026-09-17
description: 照片上傳網格疊加功能實作踩坑——上傳端點盤點、grid_size注入模式、backfill複雜度超預期
metadata:
  type: project
---

✅ 2026-09-17 上傳端功能已完成並部署驗證通過（commit `d89c0f8`）。Backfill既有素材庫照片另開任務處理，未做。

## 功能內容
使用者上傳照片時可選 原圖/4×4/5×5，後端 `apply_grid_overlay`（`src/utils/grid_overlay.py`）永久燒入等分黑色1px網格線，輔助AI辨識人物比例構圖。前端共用元件 `GridOverlayPicker.tsx` 含三選一+建議語（真人照片建議使用）+警語（永久修改請自行備份）。

## 上傳端點盤點結果（7個表面像照片上傳，實際6個是）
- `comic_gen/api.py`: `/upload`、`/projects/{}/assets/{}/{}/upload`、`/library/assets/upload`、`/projects/{}/frames/{}/upload_image`、`/projects/{}/frames/{}/upload_t2i`（串流寫檔，寫完後讀回覆寫，非攔截bytes）
- `playground/api.py`: `/playground/upload`
- **誤判排除**：`import_file_preview`(txt/md匯入非照片)、`CharacterWorkbench.tsx`的`uploadFile`呼叫(其實是音訊)、`VideoSidebar.tsx`同樣是音訊、`ConsistencyVault.tsx`的`handleUpload`是死代碼(實際走`UploadAssetModal.tsx`)。**函式名稱/檔名不能作為「是照片上傳」的判斷依據，必讀呼叫上下文與accept類型**

## 前端混合accept模式的陷阱
`MediaInput.tsx` Seedance r2v模式`accept:'image/*,video/*,audio/*'`同一個dropzone混收三種檔案；若對非圖片檔案也傳非0的gridSize會讓後端`apply_grid_overlay`對副檔名白名單報400。修法：`file.type.startsWith('image/') ? gridSize : 0`，且選擇器只在`config.accept.includes('image')`時渲染。

## Backfill範圍比預期複雜（故意排除，另開任務）
`library_assets.json`裡 Character用`reference_sheet.image_variants[]`陣列（可能多筆）、Scene/Prop用單一`image_url`；圖片可能是本機路徑或OSS簽名URL兩種來源，`oss_utils.py`只有上傳沒有下載封裝。且只能在VPS容器內對production資料操作，不能本機模擬。範圍超出「動工前置判準」，故意分離成獨立任務。

## Live驗證方法論（CORS/瀏覽器渲染器凍結繞過）
用claude-in-chrome驗證OSS圖片像素時，`crossOrigin`讀canvas遇CORS報錯會讓渲染器凍結（後續screenshot/zoom全部逾時，見[[feedback_browser_blob_download_freezes_renderer_after_few_calls_2026-09-15]]同類模式）。改用SSH從VPS容器內`docker cp`把剛上傳的檔案（`ls -t /app/output/uploads/`找最新）複製到本機，Python `Image.getpixel()`直接驗證網格線座標，比瀏覽器內像素比對可靠。
