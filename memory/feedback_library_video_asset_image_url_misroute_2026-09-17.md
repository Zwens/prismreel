---
name: library-video-asset-image-url-misroute
description: save_to_library()未依media_type分流，video輸出（如dance換裝合成）被硬塞進image_url欄位，library卡片破圖
metadata:
  type: feedback
---

✅ 2026-09-17 已修復並部署（commit `51341d6`）。

**根因**：`src/apps/playground/service.py` 的 `save_to_library()` 不論 `target_output.media_type` 為 image 或 video，一律把 `dest_path` 寫入 `image_url`。`src/apps/comic_gen/pipeline.py` 的 `create_library_asset()` 也只接收 `image_url` payload key，Scene/Prop model 雖然 Prop 本就有 `video_url` 欄位（Scene 沒有純字串 `video_url`，只有 `video_assets: List[VideoTask]`），但建立時從未被填入。前端 `AssetLibraryPage.tsx`/`AssetInspector.tsx` 也只讀 `image_url`/`image_asset`，完全沒有 `<video>` fallback。

**修法**：
1. `save_to_library()` 依 `target_output.media_type == "video"` 分流，傳 `video_url` 而非 `image_url`
2. `create_library_asset()` 補上 `video_url` 參數，Prop 分支接收（Scene 分支不接受——Scene model 無對應純字串欄位，且目前無 scene 類影片輸出來源，暫不擴充）
3. 前端 `projectStore.ts` 補 `Prop.video_url?: string` 型別；`AssetLibraryPage.tsx` 卡片網格 + `AssetInspector.tsx` 詳情 hero 兩處都補 `<video muted loop playsInline autoPlay>` fallback（`image_url`/`image_asset` 都空但 `video_url` 有值時觸發）

**舊資料 backfill（2026-09-17 當場處理，非自動）**：掃描 VPS `/app/output/library_assets.json` 找出 `image_url` 副檔名為 `.mp4/.mov/.webm` 的 prop/scene 記錄，只查到一筆 `prop_ac6600d4ef73`（scene 沒有，因為 scene 走不到 video 分支）。手動改 JSON（先備份 `.bak.<timestamp>`）把 `image_url`搬到`video_url`並清空 `image_url`，改完必須 `docker restart prismreel-backend` 讓 in-memory pipeline singleton 重新讀檔，否則下次 autosave 會把記憶體舊狀態覆寫回檔案，backfill 白做。

**Why**：`create_library_asset()`/model 欄位是給圖片素材設計的舊介面，video 輸出（dance-swap 換裝合成）是後來加的功能，資料流串接時漏了 media_type 判斷這一步；另外 `_category_to_asset_type()` 把 dance 模組傳的 `category="general"` fallback 成 `"prop"`（設計如此，非bug），兩個因素疊加才導致換裝影片被歸進「道具」分類且欄位錯置。

**How to apply**：
1. 日後任何「把 playground 輸出存進 library」的新輸出類型（如未來的音訊），都要檢查 `create_library_asset()`/Character/Scene/Prop model 有沒有對應欄位，不能預設全部走 `image_url`
2. 改 `library_assets.json` 這類 pipeline singleton 持久化檔必配 restart，光改檔案不夠，否則下次 autosave 會用記憶體舊值覆寫回檔案
3. live 驗證優先用 `fetch('/library/assets')` 確認欄位值 + `document.querySelectorAll('video')`/`querySelectorAll('img')` 過濾 `naturalWidth===0` 確認畫面渲染，比純肉眼截圖更可靠且可程式化重跑

**畫面驗證（claude-wmzic-6c 2026-09-17 live複核）**：DOM查詢確認`prop_ac6600d4ef73`卡片渲染出`<video>`元素且正確載入mp4 src，全頁`brokenImgCount: 0`。問題徹底結案。
