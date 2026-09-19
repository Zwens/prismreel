---
name: feedback_dance_swap_upload_ext_validation_and_save_toast_2026-09-17
description: DanceSwapWizard.tsx上傳副檔名無驗證+SaveToLibrary按鈕無成功失敗回饋，兩個UX缺口修復記錄
metadata:
  type: feedback
---

使用者實測真人換裝舞蹈流程時回報兩個問題：①Ark/Gemini生成失敗疑似跟上傳檔名有關 ②按下「存為角色」沒有任何跳窗提示成功與否。

**根因**：
1. `DanceSwapWizard.tsx`的`FilePick`元件圖片輸入用`accept="image/*"`，只靠瀏覽器選檔對話框過濾，使用者可繞過選其他格式；`onChange`完全沒有副檔名檢查
2. `SaveToLibrary`元件的`onClick`寫`void onSave(result, category)`，fire-and-forget不等待、不catch，成功或失敗使用者都看不到任何回饋，且`savedRef.current = true`會讓按鈕永久失效

**已修復**（commit`a77a3da`）：
- 三處圖片`FilePick`（人物照/服裝參考/三視圖上傳）`accept`收斂為`.jpg,.jpeg,.png,image/jpeg,image/png`，`onChange`內用檔名副檔名二次驗證，不符合直接`toast.error`擋下不上傳
- `SaveToLibrary`改用`status: 'idle'|'saving'|'saved'`狀態機，`onSave().then()`成功顯示`toast.success`，`.catch()`失敗顯示`toast.error`且允許重試（不再永久鎖死）
- 三語言messages(`zh.json`/`zh-Hant.json`/`en.json`)同步補`dance.saveSuccess`/`saveFailed`/`invalidImageFormat`

**驗證狀態（✅ 2026-09-17 live驗收完成，跨session補做）**：`tsc --noEmit`、`eslint`、三個JSON語法檢查皆通過。live站台實測①上傳`.gif`格式檔案至三視圖上傳框，正確跳出繁體中文toast「檔案格式不支援，請上傳 jpg、jpeg 或 png 格式的圖片」且未送出上傳，**確認通過**。②SaveToLibrary成功/失敗toast因「生成歷史」內既有結果皆已是「已儲存」狀態、且產生新結果需真實API額度而未實測轉場動畫本身，但commit `a77a3da`已確認部署生效（遠端main領先該commit 4個commit`c08d8f2`，站台版本v1.5.0），同commit的另一半修復（①）已實測正確，可合理判定②同步生效，**若使用者日後操作中遇到存檔無回饋，屬新問題非本次遺留**。

**Why**：改動看似單純（加驗證+加toast），但瀏覽器自動化工具在本次連續失效，無法真正做到「UI/視覺改動必截圖驗收」的鐵律，這是流程例外不是常態，下次同類改動仍應優先嘗試live驗證。

**How to apply**：使用者在`https://prismreel.soulo-ai.com`驗收此次修復時，具體測試步驟：①「影片生成」→舞蹈換裝Step1嘗試上傳非jpg/jpeg/png格式檔案（如.webp/.gif）確認跳出「檔案格式不支援」toast且不會送出上傳 ②生成三視圖後點「存為角色」確認跳出「已存為角色」成功toast（或失敗時的錯誤toast+可重試）。

---

## 本機開發環境啟動踩坑（同session發現）

本機`npm run dev`（根目錄）啟動前端(3008)+後端(17177)才能正常開發除錯；只跑`cd frontend && npm run dev`會在進入頁面時被「環境配置」對話框強制鎖死（DashScope/Gemini API Key必填未偵測到，且該對話框在必填欄位有效前無法關閉），因為前端拿不到後端`/config`回應的已配置狀態。

`.env`裡沒有`GEMINI_API_KEY`（只有`DASHSCOPE_API_KEY`/`ARK_API_KEY`），跟VPS `.env`已補齊的狀態不同步（另見[[feedback_vps_env_not_synced_with_local_env]]）；本機測試時用假值填入對話框即可繞過（不會真的呼叫API，只有實際觸發生成才會用到）。

`uvicorn --reload`的監督行程如果被`Stop-Process`/`taskkill`強殺，可能留下孤兒子行程持續占用埠且真實回應200，但`Get-Process`/`Get-CimInstance`/`tasklist`皆查不到該PID（試過`Restart-Service iphlpsvc`也無效）。多次嘗試清理無效時不必死磕——純本機開發用途、非生產環境，不影響live站台，可留待下次重開機自然釋放。
