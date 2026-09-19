---
name: grid-overlay-three-defects-ai-gen-dance-negative-prompt-2026-09-17
description: 網格疊加功能上線後三個功能性缺陷的根因與修復——AI生成/素材庫選擇不套網格、prompt未注入辨識引導文字、DanceSwapWizard排除網格checkbox缺失
metadata:
  type: project
---

⚠️ 2026-09-17 首輪三個缺陷修復（commit `20f50b5`）**結論有誤**，實際仍有兩個缺口，已在同日稍晚由另一輪修復根治，見 [[feedback_dance_swap_pickSheet_and_seedance_negative_prompt_gap_2026-09-17]]：
1. `pickSheet`（從素材庫選擇）路徑完全沒被這輪修復觸及，選圖後不會燒網格（commit `65d4f3a`修復，後又被`68d98c9`重構為`applyGridToSheet`明確觸發）
2. 排除網格checkbox勾選後送出的`negative_prompt`，Seedance後端從未讀取、Ark API本身也不支援這個概念，checkbox形同虛設（commit`a76fa95`修復，改走主prompt拼接）

以下為原始記錄，保留供脈絡參照：

## 根因
`d89c0f8`/`c08d8f2` 兩個commit把 `GridOverlayPicker` 只接在「檔案上傳」路徑；AI生成、素材庫選擇兩種來源的UI完全沒有網格選項也沒有燒網格機制——不是「選了沒生效」，是設計上就沒接。DanceSwapWizard（真人換裝舞蹈）的Step3生成模組是獨立於主playground compose流程之外的程式碼路徑（`useDanceSwap.ts`開頭註解明確寫著"Deliberately NOT wired through the shared playground compose state"），完全沒接上`c08d8f2`做的排除網格勾選框。

## 修復
1. 新增後端 `POST /playground/apply-grid`（`src/apps/playground/api.py`），複用`apply_grid_overlay`對既有本機檔案原地燒網格，用`resolve_local_media_path`限制只能操作`output/`底下路徑。
2. `useDanceSwap.ts`的`generateSheet()`：AI生成完成後若`gridSize>0`呼叫`applyGridToMedia`把網格燒進生成結果，並在`buildThreeViewPrompt`（`prompts.ts`）追加正向prompt片段引導AI辨識網格用途。
3. 新增`GRID_OVERLAY_GUIDANCE_PROMPT`常數（`usePlaygroundStore.ts`，與既有`GRID_OVERLAY_NEGATIVE_PROMPT`並列），接進主playground流程（`useGenerationRunner.ts`）+ dance流程兩邊。
4. `DanceSwapWizard.tsx`新增本地`sheetHasGridOverlay`/`appendGridOverlayNegative` state（不是共用`usePlaygroundStore`，因為dance wizard本來就用獨立state），Step3新增排除網格線checkbox。

## Live驗證方法論
用真實AI生成（非mock）驗證，因為這是全新功能純程式碼審查無法確認執行期行為。過程中一度誤判失敗：Monitor輪詢腳本用「`ls output/playground/images/`檔案數>0」當完成判定，但資料夾裡本來就有舊檔案，抓到的是先前session留下的舊檔（時間戳`03:45`），不是這次生成的新檔（`08:28`）。改用「比對UUID是否跟後端log裡`apply-grid`請求的路徑一致」才抓對正確檔案。**輪詢生成完成的判定不能只看檔案存在，要核對檔案名稱/UUID跟本次操作對得上**，否則會產生「新功能沒生效」的假陰性。

驗證方式：SSH docker cp把驗證用的圖片抓下來本機用Read工具肉眼看網格線（比色彩取樣更直覺可靠）；查`output/playground_history.json`裡對應generation id的完整prompt字串，用`'proportion grid' in prompt`確認guidance文字真的被注入。

## 相關
[[feedback_grid_overlay_upload_feature_2026-09-17]] — 原始功能實作記錄，當時的「✅已完成部署驗證」結論只驗證了上傳路徑，AI生成/DanceSwapWizard兩條路徑當時未涵蓋在驗證範圍卻沒有註明，導致誤以為全功能已完整驗證。
