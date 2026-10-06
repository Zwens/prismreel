---
name: feedback_dance_swap_real_face_needs_byteplus_asset_id_2026-10-06
description: 舞蹈換裝「又不能用」＝Ark真人審核擋圖(InputImageSensitiveContentDetected.PrivacyInformation)，非程式壞；Prismreel素材庫≠BytePlus肖像庫，需填asset ID走asset://
metadata:
  type: feedback
---

**現象**：舞蹈換裝合成失敗。查 VPS `playground_history.json`（容器內 `/app/output/`），09-29 三筆 v2v 皆 `HTTP 400 InputImageSensitiveContentDetected.PrivacyInformation`，圖是上傳 jpg/三視圖，影片根本沒開始。docker logs 無生成錯誤，錯誤只在 history 的 `error` 欄。

**Why**：使用者以為「人物放進資產庫」＝已解決，但 Prismreel 素材庫(`library_assets.json`)只存一般圖片網址，無 Ark asset id；程式也無 CreateAsset。Ark 看到的仍是一般真人臉照片。BytePlus 肖像庫是另一個系統，需拿 `asset-…` ID。

**How to apply**：commit `b409298` 在 Step 3 新增「BytePlus 肖像庫資產 ID」欄位（localStorage 記住），有效時 `input_media[1]=asset://<id>` 取代三視圖，後端 `_resolve_ark_image_url` 原本就直通。使用者資產 ID `asset-20260929175455-thnl4`（09-29 建立，尚未實測）。
**未驗證**：2.5-v2v + task_type reference 是否接受 asset:// 參考圖，需使用者實跑一次；若仍 400 先看 history error。若動作影片(非深度)含真人臉，reference_video 也可能被擋。
不協助網格疊加等干擾偵測手法（見 [[reference_seedance_real_person_face_restriction_and_asset_library]]）；09-29 帶網格提示詞仍被擋。
