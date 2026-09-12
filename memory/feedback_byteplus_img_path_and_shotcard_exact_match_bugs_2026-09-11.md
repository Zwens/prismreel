---
name: byteplus-img-path-and-shotcard-exact-match-bugs
description: BytePlus/Ark首末幀本機檔案未接上provider_media半成品 + ShotCard.tsx三處字串比對繞過既有容錯函式重演舊bug
metadata:
  type: project
---

2026-09-11 修復三個圖片抓取失效問題：

1. **byteplus.py 缺 img_path 處理**：`BytePlusVideoModel.generate()` 只認 `img_url`，本機上傳的 first_frame/last_frame（`img_path`）被靜默丟棄，Ark 收到空 `images` 陣列。根因是 catalog 資料層（`model_catalog/generated/model_catalog.json` 的 `seedance.transport.image_input_mode.byteplus = "byteplus_ark_image_url"`）早已定義好這個 mode，但 `provider_media.py` 的 `resolve_media_input()` dispatch 從未認得這個字串（半成品），`byteplus.py` 也從未呼叫它。

2. **ShotCard.tsx 三處精確比對重演 assetTags.ts 已修過的 bug**：`r2vSlots`／`polishImageUrls`／`castAvatars` 各自用 `characters.find(c => c.name === name)` 精確比對 `[characterN:name]` 標籤，只有 `referencedAssetNames`（第506行，負責點亮UI chip）套用了 `resolveAssetByTagName` 的容錯比對（exact→unique substring）。LLM 縮寫角色名稱時（如「机械鸟」vs「现代智能机械鸟」）三處精確比對會找不到對應素材，參考圖片/描述沒被送進生成流程，但UI chip卻顯示「已引用」，造成介面與實際行為不一致的假象。

**Why**：資料驅動的 provider registry 設計會讓 catalog 配置與程式碼實作出現「配置先行、實作未跟上」的落差；同一個容錯函式若沒有強制所有呼叫點共用，各處各自土砲重寫精確比對版本會逐一重演同一個 bug。

**How to apply**：
- 新增/修改 provider family 的 `image_input_mode`/`audio_input_mode` 等 transport mode 字串時，必須同步確認 `provider_media.py` 的 `resolve_media_input()` 有對應 dispatch 分支，不能只改 catalog JSON
- 專案裡若有「已知模糊比對修復函式」（如 `resolveAssetByTagName`），新增呼叫點時一律搜尋既有呼叫方式套用，禁止就地重寫 `.find(c => c.xxx === target)` 這種精確比對

**修復**：
- `provider_media.py`：`resolve_media_input()` 新增 `byteplus_ark_` mode 前綴分支，導向既有的 `_resolve_vendor_url_mode`（本機檔案→OSS上傳→簽名URL，同vidu/pixverse模式）
- `byteplus.py`：新增 `_resolve_ark_image_url()`，`img_url`/`img_path`/`last_frame_url` 統一經此解析（遠端URL直接pass-through，本機路徑走OSS）
- `ShotCard.tsx`：`r2vSlots`/`polishImageUrls`/`castAvatars` 三處改用 `resolveAssetByTagName(name, [characters, scenes, props])`

**驗收現況（2026-09-11 更新）**：frontend `node_modules` 實際完整（`typescript`/`tsc` 皆存在），`npm run dev` 可正常啟動（port 3008，curl 200）；先前記憶誤判「node_modules 安裝不完整」已過時修正。`npm run typecheck` 唯一錯誤在 `EnvConfigChecker.tsx`，經 `git diff` 比對確認與本次三檔案改動無關。真正卡住的是 claude-in-chrome 瀏覽器自動化工具本身：對 `localhost:3008`/`127.0.0.1:3008` 連續 3 次截圖回傳 `Frame with ID 0 is showing error page`（curl 確認頁面本身 200 正常），已達停損門檻，改請使用者親自瀏覽器確認 UI（未再逼近）。本次驗收完成：Python端手動整合測試 + 程式碼審查確認型別與依賴陣列正確；ShotCard.tsx 實際渲染/互動行為仍待使用者或下次視覺驗收補齊。
