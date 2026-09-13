---
name: upload-filename-is-backend-uuid-not-original
description: Playground 上傳的檔案在後端一律改名成 UUID，前端顯示的「檔名」是無意義亂碼，且與模型辨識多圖無關——模型靠陣列順序辨識，不是檔名或前端編號徽章
metadata:
  type: feedback
---

`src/apps/playground/api.py` 的 `upload_media()` 用 `filename = f"{uuid.uuid4()}.{ext}"` 儲存上傳檔案，完全丟棄使用者原始檔名。前端 `MediaInput.tsx` 一度嘗試把這個 UUID 檔名做各種顯示優化（放大字體、移出圖片、取消截斷），但無論怎麼調整 CSS，顯示的內容本身就是一串對使用者無意義的亂碼——問題出在後端命名邏輯，不是前端顯示層級能解決的。

同時查證澄清：Ark/Seedance 多圖生成（`src/models/byteplus.py` `build_ark_content()`）辨識多張參考圖靠的是 `ref_image_urls` 陣列的**先後順序**，每個 image_url 項目只標記 `role: "reference_image"`，完全不帶檔名或任何文字標籤。前端縮圖上的「Image N」徽章數字對應的正是這個陣列順序（可信賴），檔名文字則從未參與、也不可能參與模型辨識。

**Why**：2026-09-10 使用者多次反饋「檔名太小/被截斷/想縮短」，反覆調整顯示樣式四次才定案為「乾脆不顯示檔名，只留 Image N 徽章」——如果一開始就確認「檔名到底有沒有用途」，可以省掉三次白工迭代。

**How to apply**：
1. 若未來需求要「上傳後保留原始檔名給使用者辨識」，正確做法是修改後端 `upload_media()`，用 `secure_filename(file.filename)` 之類方式保留原名（另外用 UUID 做實際儲存路徑避免碰撞，回傳給前端的是原始檔名而非儲存路徑檔名），不是在前端對 UUID 做顯示優化。
2. 任何「這個標籤/文字會不會影響到後端功能」的疑問，優先查後端實際組 API payload 的程式碼（例如本例的 `build_ark_content`），不要只看前端命名或憑直覺猜測。
