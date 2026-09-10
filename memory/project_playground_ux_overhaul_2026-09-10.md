---
name: project-playground-ux-overhaul-2026-09-10
description: Playground（創作台）體驗直覺化改造進度交接——已定案兩份 plan-review 清單，尚未開始實作
metadata:
  type: project
---

## 背景

使用者已擁有 Seedance 官方 API（BytePlus Ark）+ 即夢（Tensor/DashScope）API，目標是把 PrismReel Playground 升級到能取代原本購買的第三方 AI 影片生成平台（對標即夢/可靈類），不需再額外付費買第三方工具。

使用者回報 6 個問題，經實測逐一定性：
1. 圖片上傳空間缺失 → **已存在**（`MediaInput.tsx`），只在 i2i/i2v/r2v 模式顯示，藏得深
2. 影片擺放空間缺失 → **已存在**，v2v「編輯」模式下顯示，支援拖拽上傳+從資產庫選取
3. 缺乏文字塊+圖片塊+影片塊連線的工作流編輯器（ComfyUI 風格）→ 確認不存在，**架構級新功能，另案處理，不在本次兩份清單範圍內**
4. 無法多圖配多文 → **已存在**，r2v 模式最多 9 張參考圖 + 一段 Prompt
5. 選擇不夠明確 → **真實痛點**，6 種生成模式用術語縮寫按鈕（t2i/i2i/t2v/i2v/r2v/v2v）分兩排小按鈕，看不出差異，且左側面板固定 420px，多個 section 堆疊需捲動才能看到全貌
6. 無法選 Seedance 模型 → 模型選單本身能選到 12 個 Seedance 型號，**真正缺口是 `EnvConfigDialog.tsx` 環境配置表單完全沒有 Ark API Key 的填寫欄位**（型別已定義 `ARK_API_KEY`/`ARK_REGION` 但 JSX 沒刻對應區塊），選了也大概率因無金鑰失敗

## 已定案、待實作的兩份 plan-review 清單（scratchpad，已過 Step 2A/2B 壓力測試）

**注意**：這兩份清單目前存在 session 的 scratchpad 目錄（`C:\Users\chenc\AppData\Local\Temp\claude\...\scratchpad\`），**temp 目錄可能被系統清理**，下一輪接手時第一件事：確認這兩個檔案還在，若已被清掉，需要根據下方摘要重新用 plan-review skill 走一次（不可省略壓力測試直接實作，因為過程中曾兩度推翻自己的初版假設）。

### 清單 1：`plan-review-playground-ui-intuitive.md`（優先，使用者已確認方向）

方案：`PlaygroundPage.tsx` 引入頁面級狀態 `playgroundStage: 'select' | 'compose' | 'results'`。
- `select`：新建 `ModeCardSelector.tsx`，6 張卡片（圖示+白話說明取代術語按鈕），點擊設定 `mode` 並進入 `compose`
- `compose`：全寬工作區，Prompt/素材輸入/模型/參數同時可見不需捲動（暫不渲染 `ResultGallery`）
- `results`：現有左右分欄+結果畫廊，使用者按下生成鈕**當下**（`handleGenerate` 觸發,不等非同步 `dispatchRequest` 完成）就切換過來，避免體感延遲；保留「切換生成類型」入口返回 `select`

查證過程推翻的兩個原始假設（重新實作前務必知道,避免重蹈覆轍）：
1. 原方案以為「捲動迷宮」是因為功能藏在深層摺疊區,實際查 `PlaygroundPage.tsx` 後發現各模式素材輸入本來就展開可見（`showMediaInput` 邏輯本已處理),真正問題是「420px 窄欄堆疊多個 section 總高度超過視窗」,單純換掉按鈕列不能解決捲動問題,必須同時做版面級改造（雙狀態切換,而非只加寬側欄）
2. 視圖切換時機原訂在非同步 `dispatchRequest` 完成後，會造成使用者點擊生成鈕到畫面反應之間的空窗體感，已修正為 `handleGenerate` 呼叫當下立即切換

已查證安全事項：`ResultGallery.tsx` 本地 `viewMode` 狀態與資料流不依賴掛載狀態,隱藏它不影響背景輪詢（輪詢邏輯在 `PlaygroundPage` 的 `pollTimers`）；Grep 確認 `ModeSelector`/`MediaInput`/`ModelSelector`/`ParameterBar`/`PromptInput` 只被 `PlaygroundPage.tsx` 引用,無其他頁面共用會被波及。

### 清單 2：`plan-review-playground-ark-key.md`（次要,先做清單 1）

方案：`EnvConfigDialog.tsx` 新增獨立「Seedance / Ark」表單區塊——**不可套用 Kling/Vidu 的 DashScope/Vendor Direct 雙模式模板**（已查證 `src/models/byteplus.py` 檔頭注解確認 Ark 只有官方直連一種模式,無代理選項),改為：`ARK_API_KEY`（必填輸入框)+ `ARK_REGION`（intl/cn 二選一按鈕,語意是地區非 Provider Mode)。同時補上原計畫漏列的 `ARK_BASE_URL`（後端 `api.py:1333-1335` 其實有三個變數,不是兩個)到 `ENDPOINT_PROVIDERS` 進階端點清單。`EnvConfigDialog.tsx` 是唯一需要修改的表單(已 Grep 確認 `EnvConfigChecker.tsx`/`SettingsPage.tsx`/`ProjectClient.tsx` 都只是掛載點,非獨立表單)。

## OSS 雲端儲存開通 — 已擱置,未購買任何方案

- 本機 `.env` 與 VPS 正式站 `.env` 皆確認 OSS 相關 4 個變數（`ALIBABA_CLOUD_ACCESS_KEY_ID`/`_SECRET`/`OSS_ENDPOINT`/`OSS_BUCKET_NAME`）**未配置**，目前所有生成結果落地存在本機/VPS 磁碟（`output/`），非雲端
- 使用者阿里雲國際站帳號完全沒開通過 OSS，控制台「立即開通」按鈕的 `href` **固定寫死指向深度冷歸檔套餐購買頁**（`planCode=package_osscombine_intl`），不是純服務啟用/pay-as-you-go 入口，這是阿里雲頁面本身的行為，非操作錯誤
- 深度冷歸檔（Archive Storage）**不適合**素材庫用途（取回要付費+等數小時解凍），素材庫應選**標準儲存**
- 找到另一條路徑：`common-buy-intl.alibabacloud.com/?commodityCode=oss_bag_intl`（資源套件購買頁,非套餐固定頁）,裡面有「標準-同城冗餘儲存」/「標準-本地備援儲存」等可選類型,本地備援最小規格 40GB/6個月僅 $0.99
- 使用者最終選擇：**先不買，暫緩處理其他問題**。下一輪如果要繼續：不確定買這個資源套件是否等同完成 OSS 服務開通（未經官方查證），建議先查阿里雲官方文件或客服確認,不要直接假設購買=開通就下手
- 本地冗餘 vs 同城冗餘判斷：素材庫非交易核心資料,可用區故障頂多暫時無法訪問不會遺失,建議先選較便宜的本地冗餘,之後有更高可用性需求再轉換

## 環境現況（下一輪接手可直接沿用,不需重建）

- 本機 `.env`（`AI 短片系統 Prismreel/.env`）已有測試用 auth 變數 + `DASHSCOPE_API_KEY='sk-test-placeholder-for-ui-audit'`（假值,僅用於通過環境配置必填檢查,無法真實呼叫）
- 本機測試帳號：`admin@test.local` / `TestAdminPass123`
- 後端啟動：`set -a && source .env && set +a && "/c/Users/chenc/AppData/Local/Programs/Python/Python312/python.exe" -m uvicorn src.apps.comic_gen.api:app --port 17177 --host 0.0.0.0`
- 前端啟動：`cd frontend && npm run dev`（port 3008，hash routing `#/playground` 進創作台）
- VPS 正式站 `ARK_API_KEY` 已配置好（見 `/opt/prismreel/.env`），本機未配置
