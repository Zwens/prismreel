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

## 待辦
尚未確認：Prismreel後端目前組prompt的實際程式碼位置——下次任務可直接搜尋後端專案中組multi-image prompt的邏輯段落，改成`Image N`格式並實測驗證。
