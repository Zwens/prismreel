---
name: dance-swap-multi-ref-image-role-confusion-and-model-choice
description: 三視圖生成人物照/服裝照角色混淆修復 + compose步驟新增Seedance 2.0/2.5模型選擇
metadata:
  type: project
---

## 三視圖生成人物/服裝混淆（✅ 已修復並部署，commit `012572c`）

**現象**：使用者上傳人物照+服裝參考照，按「AI生成三視圖」，結果生成出來的三視圖用了服裝照裡的人物臉孔/身形，不是使用者自己。已產生一次真實付費 Gemini API 呼叫（HK$1.10）浪費在錯誤結果上。

**根因**：`frontend/src/components/modules/playground/dance/prompts.ts` 的 `buildThreeViewPrompt()` 全程只用單數「the reference image」，即使 `generateSheet()` 實際送了兩張參考圖（`useDanceSwap.ts` 第 251 行 `refs = [portraitPath, outfitRefPath]`），prompt 文字完全沒有告知模型「哪張圖扮演什麼角色」。模型收到兩張圖但指示是單數，會自行判斷主體，這次判斷錯了。

**這類 bug 的辨識特徵**：呼叫**成功**、正常計費、沒有任何錯誤訊息或例外——純粹是「模型選錯了主體」，不會被任何既有的錯誤處理機制攔截，只能靠人工看輸出結果才會發現。

**修復**：`buildThreeViewPrompt()` 新增 `hasOutfitRef` 參數，兩張圖時明確生成「第一張=人物（臉/髮/身形），第二張=只取服裝款式，忽略其中的人物」的 prompt 文字。

**排查後確認無同類問題的路徑**（用作日後同類坑點的比對基準）：
- compose 步驟（`buildComposePrompt`，1影片+1圖片）：已明確區分「reference video=動作」「reference image=角色」，不會混淆
- 通用 Playground 多圖模式（t2i/r2v，最多9張）：prompt 是使用者自己手寫，UI 已有 `prompt.multiImageHint` 提示用「Image 1」「Image 2」指名，責任在使用者本人
- `comic_gen/api.py`：沒有多圖參考邏輯

**通用教訓**：系統代寫模板 prompt（非使用者手寫）+ 送多張參考圖時，必須明確告知模型每張圖的角色分工，不能假設模型會自己猜對。日後任何新增「系統組合多圖送給圖片/影片模型」的功能，動工前都要檢查 prompt 是否有角色指示。

## Compose 步驟新增模型選擇（✅ 已部署，commit `4372925`；2.0 v2v 效果未驗證）

**背景**：舞蹈換裝 Step 3 合成步驟原本寫死 `COMPOSE_MODEL = 'seedance-2.5-v2v'`，使用者要求能選其他模型。

**查證結果**：整個 model catalog（`config/model_catalog/families/seedance.yaml`）裡具備「參考影片驅動動作+角色圖合成」能力（v2v/VideoEditing）的模型**只登記了 seedance-2.5 一個**，且 `status: hidden`（不進一般模型選單）。

`docs/api-reference/byteplus-ark-seedance-seedream.md` §五.2「待核實」已記錄一個關鍵衝突：BytePlus 上游 `/models` 端點回報 Seedance 2.0（含 2.0/2.0-fast/2.0-mini）**也**聲稱支援 `VideoEditing`/`VideoExtension` task_type，但官方 API 文件的 `omni_reference_task_type` 參數**只列 2.5**；`src/models/byteplus.py` 第 418 行註解證實「2.0 直接拒絕這個欄位」（已實測過，不是猜測）。也就是說 2.0 若要走 v2v，只能不送 `task_type`，靠廠商自己的 `auto` 判定，行為未知。

**修復**：
- `src/models/byteplus.py` `ARK_MODEL_IDS` 新增 `seedance-2.0-v2v` → `dreamina-seedance-2-0-260128`，**刻意不加入** `ARK_OMNI_TASK_TYPE_MODELS`（避免送出會被拒絕的欄位）
- `useDanceSwap.ts` 新增 `COMPOSE_MODEL_OPTIONS = ['seedance-2.5-v2v', 'seedance-2.0-v2v']` 與 `state.composeModel`，取代寫死常數
- `DanceSwapWizard.tsx` Step 3 新增模型選擇按鈕，選 2.0 時顯示「尚未驗證」提示文字（三語言 i18n 已補：`step3.model` / `step3.modelUntestedHint`）

**⚠️ 未完成事項**：2.0 走 v2v 是否真的能正確用參考影片驅動動作（而非隨機生成不相關內容）**從未實測**，UI 上線但效果完全未知，需使用者手動測試判斷。

**部署驗證方法**（供日後同類排查參考）：VPS 上原始碼比對 + 前端實際 build 產物（`docker exec prismreel-frontend grep <新字串> /usr/share/nginx/html/_next/static/chunks/*.js`）雙重確認，避免只看容器重啟時間戳就誤判部署生效——nginx 是靜態匯出服務，不是 Next.js runtime，路徑是 `/usr/share/nginx/html`，`/app` 或 `.next` 目錄不存在於這個容器。
