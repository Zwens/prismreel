---
name: r2v-ref-image-urls-bypassed-resolver
description: R2V模式ref_image_urls完全繞過_resolve_ark_image_url，本機上傳圖片路徑直送Ark造成400，同修復範圍內遺漏
metadata:
  type: feedback
---

2026-09-11 fix/video-gen-image-capture 分支已修 img_path/first_frame/last_frame 的本機檔案解析，但commit 78826a3當時漏掉R2V模式的 `ref_image_urls`——`generate()` 裡 `elif img_url` 分支才走 `_resolve_ark_image_url`，`if ref_image_urls` 分支直接用原始值，導致R2V模式上傳本機圖片時被Ark回400（截圖使用者實測命中：`seedance-2.5-r2v`，images=1，400 Bad Request）。

**Why**：加新解析函式時只想著「這次要修的那條路徑」（first/last frame），沒有反查同一個 `generate()` 內是否還有其他分支也吃本機路徑但沒套用新函式；`ref_image_urls` 來源是 `service.py` 的 `gen.input_media`（本機相對路徑，如 `output/playground/uploads/xxx.jpg`），跟 `img_path` 是同一種資料形狀，理應同步處理。

**How to apply**：
- 修「某個輸入來源的本機路徑解析」bug時，先grep同一個 `generate()`/呼叫鏈內所有讀 `kwargs.get(...)` 的分支，逐一確認是否也吃得到本機路徑，不能只看使用者回報的那個模式
- 排查「400 Bad Request 發生在帶圖片時」這類問題，先用 `docker compose exec backend python3 -c "..."` 直接對vendor API重放請求，比對純文字payload（驗證key有效）vs 帶圖片payload（找出真正壞掉的欄位），不要停在「可能是key」的臆測層級
- VPS用rsync非git clone，`git log`查不到VPS版本；改用`grep`比對VPS檔案是否含新函式名稱來確認部署狀態

**修復**（commit fa69203，`fix/video-gen-image-capture`分支）：`raw_ref_image_urls` 迴圈內每個 `raw_ref` 先經 `self._resolve_ark_image_url(raw_ref, model_name=model_name)` 再收進 `images`；已用mock測試驗證本機路徑轉簽名URL、遠端URL原樣通過兩種case。

**驗收現況**：Python語法檢查通過 + mock整合測試通過（驗證resolver被正確呼叫、本機路徑/遠端URL兩種輸入行為正確）；未跑真實Ark API端對端測試（需真實OSS簽名URL可公開存取才能驗證Ark真的收得到圖）。分支已push，MR未建立（見同目錄 `feedback_byteplus_img_path_and_shotcard_exact_match_bugs_2026-09-11.md`）。
