---
name: project-digital-character-handoff-2026-09-15
description: Seedance官方Digital Character Library整合任務交接——使用者回報2個未解決問題（第1張角色破圖、角色清單不完整），前一session因context滿載交接
metadata:
  type: project
---

## 背景

任務：整合BytePlus Seedance官方Digital Character Library到Prismreel，繞開卡住的企業實名認證。完整技術脈絡見 [[reference_seedance_real_person_face_restriction_and_asset_library]]。

已完成並推送上線的commit（`AI 短片系統 Prismreel` repo main分支）：
- `cd50c38` 後端`_resolve_ark_image_url()`讓`asset://`直通不經OSS
- `bbe38b1` 新增`GET /playground/official-characters` API
- `0888248` 前端`AssetPickerModal`新增「官方角色」分頁
- `2125451` 修正縮圖來源（原抓到SPA殘留播放圖示非真人照）+ 從1筆擴充到60筆 + 改用本機下載壓縮縮圖（BytePlus簽名URL 12小時過期不能存死）
- `ff4fed3` 修正mount順序bug（`/files/digital-characters`被既有廣義`/files`掛載攔截導致404）

全部commit已通過GitLab CI（pipeline #44663等），已在live驗證過：
- `GET /playground/official-characters` 回傳60筆，200 OK
- `GET /files/digital-characters/asset-20260225015229-d77t9.jpg` 回傳200 image/jpeg
- 瀏覽器AssetPickerModal官方角色分頁截圖確認多國籍角色縮圖正確顯示（非播放圖示）

## 🔴 使用者回報的2個未解決問題（2026-09-15，交接時當場指出）

1. **第1張破圖**：官方角色分頁清單中第一張縮圖顯示異常（使用者原話「好像有破圖」）。前一session最後一次截圖看起來60張都正常，但使用者在自己瀏覽器裡看到第一張有問題——**需重新截圖或詢問使用者具體是哪個角色/什麼異常樣貌**，不要假設是同一顆bug重演（先前紫色播放圖示bug已修好，這次未必同因）。
2. **角色未完全**：使用者原話「好像人物模型角色並未完全」，可能指：
   - 官方Digital Character Library總數遠超過目前抓到的60筆（前一session滾動抓取時視窗有持續增長跡象，Spain/Saudi Arabia/Brazil/Nigeria等新國籍不斷出現，很可能有100+筆未抓完）
   - 或是指某些角色的資料欄位（如biography、tag）顯示不完整
   - **需先問清楚使用者具體指的是哪一種**，不要自行猜測範圍再動工

## 技術參考（供接手時查閱）

- 資料來源：BytePlus不提供公開清單API（`ListMediaAssetGroup`只回傳私有My assets，非公開角色庫）；改用瀏覽器頁面React fiber tree直接讀取渲染資料（`img.alt`含年齡字串定位DOM節點→往上7層fiber.return找到`children`陣列→每個`item`含`SID`/`Content.Image[0].AssetID`/`Content.Image[0].URL`/`Metadata`/`Description`）
- 縮圖下載卡點：瀏覽器`a.click()`觸發多次下載會被Chrome防護擋掉（第二次起全部靜默失敗），最終改用本機HTTP server（`http.server`監聽`127.0.0.1:8765`）接收頁面`fetch POST`過來的base64壓縮圖片（200px JPEG q0.7，平均8KB/張），繞開瀏覽器下載限制
- 資料存放：`config/digital_characters/official.json`（角色metadata，含`thumbnail_path`相對路徑）+ `config/digital_characters/thumbnails/*.jpg`（60張本機縮圖）
- 後端讀取邏輯：`src/apps/playground/api.py` `_load_official_characters()` 讀json組出`/files/digital-characters/<id>.jpg`完整URL
- 靜態掛載：`src/apps/comic_gen/api.py` 第181-194行，**必須排在廣義`/files`掛載之前**（Starlette Mount是註冊順序比對非最長前綴優先，已用TestClient最小重現案例驗證）

## 建議下一步

1. 先問使用者具體重現「第1張破圖」——是哪個角色（截圖或描述外觀）、在哪個頁面/情境看到
2. 先問使用者「角色未完全」具體指什麼——總數不夠、還是某些角色資料缺欄位
3. 若確認是總數不夠：可考慮改良抓取腳本，透過持續滾動+多輪fiber讀取拿到官方庫全部角色（BytePlus無公開API，只能靠瀏覽器自動化重複本次手法）
4. 若確認是新的顯示bug：先用DOM層級驗證（`img.complete`/`naturalWidth`/`content-type`）排除是截圖工具問題還是真實渲染問題，本次教訓是「截圖看起來異常不代表真的異常，也可能截圖看起來正常但user瀏覽器裡真的異常」——兩種方向都要留意，不能只信任其中一種驗證管道
