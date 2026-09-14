---
name: reference-seedance-multi-image-prompt-reference-syntax
description: Seedance/ModelArk 視頻生成API多圖輸入時，prompt文字裡如何正確引用對應圖片；@Image1語法僅限Playground網頁UI，API呼叫需用不同格式
metadata:
  type: reference
---

## 問題現象
Prismreel後端API呼叫已把多張圖片放進`content`陣列（多個`image_url`元素），但prompt文字裡沒有正確引用對應關係，模型無法判斷哪段描述對應哪張圖，導致角色/服裝/場景在多圖生成時對應錯亂。

## 根因：兩種引用語法不可混用，`@`語法在API呼叫中不生效
1. **`@Image1`（無空格，@開頭）**——這是官方 **Model Playground網頁UI專屬**的互動功能：使用者在Playground點擊素材縮圖，前端自動幫你把`@素材名稱`插入輸入框。這是網頁前端的UI糖衣，不是REST API的正式解析規則。
2. **`Image 1`（有空格，序數詞，無@）**——這才是官方REST API範例實際使用的格式，索引對應`content`陣列中「同類型元素（image_url/audio_url等）」出現的**順序位置**，不是asset_id、不是檔名。

官方API呼叫範例（`Private virtual portrait library`文件）：
```
"text": "...the CEO from Image 1 accidentally bumps into the female lead wearing the outfit from Image 2 (character from Image 3)..."
```
中文版官方範例混用中文敘述+中括號變體「【Image 1】」也出現過，核心規則不變：**序數詞+空格，依content陣列中該類型素材的出現順序對應，不加@**。

## 修正方式
Prismreel後端組prompt時，若走API直接呼叫（非Playground手動操作），一律使用`Image N`格式（N為該圖片在content陣列image_url元素中的順序，從1開始），不要使用`@Image1`。

## ✅ 已查證：後端不做任何prompt自動組裝，問題出在前端UI缺提示（2026-09-14已修復並上線）
`src/models/byteplus.py`的`build_ark_content()`只是把`prompt`原封不動放進text欄位，**完全沒有自動生成`Image N`或`@ImageN`標籤的邏輯**（一路從`gen.prompt`直傳到`generate()`，中間無轉換）。這代表「待辦：搜尋後端組prompt程式碼位置並修正」這個原始假設方向是錯的——不是後端字串拼接有bug，而是**使用者自己手打prompt時要遵守正確語法，但Prismreel自製的Playground textarea（`PromptInput.tsx`）沒有任何提示**，容易誤用只在Ark官方Playground網頁生效的`@Image1`語法。

（註：R2V/ComicGen產線走的是完全不同的`[characterN:name]`自訂標籤系統，見`frontend/src/lib/assetTags.ts`，跟Seedance官方`Image N`語法互不衝突、不要混淆。）

**修復**：`PromptInput.tsx`讀取`inputMedia.length >= 2`時，在textarea下方顯示提示文字（三語言i18n key `playground.prompt.multiImageHint`），說明正確格式。已commit `60c57e8`、pipeline 44209 success、live bundle已確認含正確中英文案。
瀏覽器端到端驗證因登入態（DashScope Key對話框+後端401導致登出）卡住，經使用者同意改採程式碼審查+live JS bundle文字比對收尾，未做完整UI截圖。
