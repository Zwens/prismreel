---
name: dance-swap-pickSheet-and-seedance-negative-prompt-gap-2026-09-17
description: DanceSwapWizard網格疊加兩個殘留缺口的根因——pickSheet未接燒網格、Seedance/Ark不支援negative_prompt導致checkbox形同虛設
metadata:
  type: feedback
---

✅ 2026-09-17 兩個缺口已修復並三層live驗證通過（commit `65d4f3a` + `a76fa95`）。

## 缺口1：pickSheet 從未接上燒網格邏輯
`generateSheet`（AI生成）、`uploadSheet`（本機上傳）都在`20f50b5`那輪接了`gridSize`並燒網格，但`pickSheet`（從素材庫選擇）完全沒有`gridSize`參數，是三條路徑裡唯一被漏掉的一條。同類任務盤點多個並行入口點時，逐一列出**所有**呼叫路徑並逐一核對，不能驗過其中兩條就推論第三條「應該也一樣」。

## 缺口2（更深層）：negative_prompt對Seedance/Ark完全無效
使用者勾選「排除網格線」checkbox後，前端把消除文字塞進`negative_prompt`參數送出，但這個參數在Seedance路徑上是死路：
1. `service.py`的`_generate_video_seedance()`組裝送給Ark的kwargs時，從未讀取`gen.negative_prompt`（對照同檔案的`_generate_video_wanx()`有明確帶上這個欄位，兩者處理不一致）
2. 就算補上①，ByteDance Ark的Seedance API本身**沒有negative prompt這個機制**，只吃`prompt`一個文字欄位——`negative_prompt`是Kling/Gemini等其他模型家族才有的概念，不是通用API設計

**修法**：不強行修`negative_prompt`傳遞鏈，而是把排除意圖改用正向措辭拼進主`prompt`（新增`GRID_OVERLAY_EXCLUDE_PROMPT_SUFFIX`常數），因為`prompt`才是Seedance唯一會讀的欄位。

**教訓**：checkbox/UI狀態存在且被正確設定，不代表這個值真的被下游模型使用。驗證UI功能是否生效時，要往下追一層「這個值最終有沒有被送到真正會用它的API欄位」，不能只驗證到「有沒有被塞進某個parameter」就停止。跨模型家族共用的prompt-injection功能（如這次的網格疊加），每加一個新的模型家族/呼叫路徑，都要重新確認該模型的API實際支援哪些欄位，不能假設所有路徑都吃同一組參數。

## Live驗證方法論（避免誤判CI是否生效）
GitLab shell-executor runner在VPS上會有多個並發`builds/<runner-token>/<slot編號>/`目錄，slot編號不保證遞增或固定對應「最新」——**判斷本次CI用的是哪個slot，唯一可靠方法是逐一核對每個slot目錄的`git log -1`是否等於目標commit**，不能憑經驗假設「數字最大的就是最新」或沿用上次驗證時查過的slot編號（上次是2，這次變成0，兩次認知不一致）。

三層證據鏈完整驗證順序：① gitlab-runner build slot的git HEAD → ② `/opt/prismreel`部署目錄原始碼 → ③ 容器內實際運行的JS bundle（用`grep -l`關鍵字先定位對應chunk，因為Next.js chunk hash會隨內容變化，不能沿用上次記的檔名）。字串命中次數本身不能證明「哪個呼叫方接上了」，需要抓呼叫點的完整上下文（如`pickSheet(e,er)`雙參數特徵）才能區分修復前後版本。

## 相關
[[feedback_grid_overlay_three_defects_ai_gen_dance_negative_prompt_2026-09-17]] — 首輪修復記錄，其「三缺陷已修復」結論已在此檔更正
