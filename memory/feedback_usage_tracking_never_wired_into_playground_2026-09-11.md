---
name: usage-tracking-never-wired-into-playground
description: 用量追蹤功能只接了pipeline.py漫畫生成流程，Playground完全沒有user_id/usage_events串接，一度被記憶誤記成「已完成並上線」
metadata:
  type: project
---

2026-09-11 使用者實測 `/usage` 頁面完全沒有數據、生成前無費用預估、影片無標記費用，追查後發現：`feature/usage-tracking` 分支（含 `/usage` 頁面、`usage_repo.py`、admin dashboard）的合併狀態一度誤判為「已上線」，但即使真正合併進 main 之後，這套用量追蹤系統本身也**只接了 `src/apps/comic_gen/pipeline.py`（漫畫/劇本生成流程）**，`src/apps/playground/` 這條完全獨立的路徑（Playground 頁面，使用者測試 R2V/I2V 首幀生影片用的介面）從未被納入範圍。

**根因鏈（逐層確認）**：
1. `playground/api.py` 的 `/generate` 路由完全沒有 `Depends(auth.require_login)`，Playground 整個 API 無身份驗證
2. `PlaygroundGeneration` 資料模型沒有 `owner_id` 欄位，連「誰生成的」都沒記錄
3. `service.py` 四個 `_generate_video_*`（wanx/seedance/kling/vidu）呼叫 `model.generate(...)` 後**完全丟棄回傳值**，即使 `BytePlusVideoModel.generate()` 早已回傳 `(output_path, elapsed, usage)` 三元組（usage 含真實 `total_tokens`）
4. 因此 `usage_repo.record_generation_usage()` 在整個 `src/` 沒有任何一處被 Playground 呼叫過，`usage_events` 表存在但永遠 0 筆

**Why**：用量追蹤設計文件（`docs/plans/2026-09-11-usage-tracking-design.md`）Scope 段落只提到 `ScriptProcessor`/`pipeline.py` 的呼叫鏈分析，完全沒有提及 Playground 這條平行路徑存在；規劃階段以「主要生成入口」為範圍，漏了測試用的獨立 Playground 介面。

**How to apply**：
- 新功能涉及「串接到所有生成路徑」時，先用 `grep -rln "model.generate\|\.generate("` 掃過全部呼叫點，不能只認一條主流程
- 判斷「功能是否已上線」不能只看 `/usage` 頁面存不存在，要查 `usage_events` 表實際筆數 + 逐一確認每個生成入口是否真的呼叫了記錄函式

**本次修復**（分支 `feat/playground-usage-tracking`，MR: https://gjseo.qit1.net/prismreel/prismreel/-/merge_requests/new?merge_request%5Bsource_branch%5D=feat%2Fplayground-usage-tracking）：
- `PlaygroundGeneration.owner_id` + `PlaygroundOutput.total_tokens`/`cost_usd` 新增欄位
- `/generate` 加 `Depends(auth.require_login)`（無 `JWT_SECRET` 時退化匿名 admin，不影響單機模式）
- 四個 `_generate_video_*` 改回傳 `Optional[dict]` usage 資訊；只有 BytePlus 有 `total_tokens`，其餘三家維持 count-only（符合設計文件排除範圍）
- 新增 `/playground/estimate-cost` 端點 + `usage_repo.estimate_seedance_cost_usd()`：用 Ark 官方公式 `duration * width * height * fps / 1024` 從 resolution+duration 反推 token 數做生成前估算，已用真實 VPS 資料驗證（720p/5s/24fps 實際 108654 tokens vs 估算 108000，誤差 0.6%）
- 前端：`CostEstimate.tsx` 防抖顯示預估費用；`ResultCard.tsx` 顯示已完成影片的實際費用
- 端到端測試：`create_generation(owner_id)` → 生成 → `usage_repo` 寫入 → `get_user_usage_summary` 查詢全鏈路已驗證（用真實 SQLite schema，非純 mock）

**未做**：圖片生成（T2I/I2I）的用量記錄——沿用設計文件排除範圍（image.py 無已確認定價表），不擴大範圍。
