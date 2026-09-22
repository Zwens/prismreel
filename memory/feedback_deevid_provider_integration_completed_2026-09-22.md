---
name: deevid-provider-integration-completed
description: DeeVid Quality V4.0影片生成provider整合+月度點數額度系統完成merge進main
metadata:
  type: project
---

Prismreel 新增 DeeVid（`api.deevid.ai`）Quality V4.0 image-to-video provider，並實作 600 點/週期（每月 20 日重置）的額度追蹤機制，硬擋額度用盡後的新生成請求。commit `1f78d74`（含 `631531f` 主體實作+最終審查修復）已 merge 進 main 並 push。

**Why**：使用者要把 DeeVid API 接進既有 Seedance/Kling/Vidu 多 provider 架構，僅 image-to-video、僅 Quality V4.0 model；DeeVid 官方 API 無點數餘額查詢端點，只能本地依 `duration × 4` 公式估算並記帳於獨立新表 `credit_ledger`（不動既有 `usage_events` 統計表）。

**動工前查證推翻原始假設**：原計畫誤植的 model 名稱 `"Quality V4.7"` 經實際呼叫 `GET /v1/open-api/image-video/models` 確認不存在於 DeeVid 系統，改用 `"Quality V4.0"`；duration 範圍對應修正為 4-15 秒（非原假設 1-30 秒）；圖片輸入為兩步驟（先 `POST /file-upload/upload/image` 取得 `userImageId`，再用該 ID 提交任務，非直接傳圖片 URL）。這些修正已同步進 spec/plan 文件與程式碼。

**How to apply**：日後任何「使用者記憶中的 API 版本號/模型名稱」在動工前，一律以帳號實際 API 呼叫結果為準，不可只憑使用者提供的文件截圖/範例當最終真相（本案文件範例與實際 API 回應恰好一致，但兩者都需要與程式碼實作前的即時查證交叉確認）。另見 [[feedback_new_video_provider_must_register_provider_media_dispatch_2026-09-21]]——新增 provider 除了 model catalog YAML + adapter + service.py dispatch，還要碰 `provider_media.py` 的硬編碼 dispatch 白名單。

**Task 8（端到端真實 API 驗收，會消耗 20 點真實額度）使用者明確選擇跳過**，Task 1-7 視為計畫完成。殘留風險：DeeVid 真實 submit/poll 回應欄位名稱（`userImageId`/`resultVideoUrl`/`SUCCESS`/`FAILED`）僅對照 `GET /models` discovery 端點與廠商文件驗證過，從未經過真實 submit round trip 確認，日後若要執行 Task 8，須斷言真實回應欄位名稱而非只確認影片有生成。

另發現一個既有系統缺口（非本次引入）：`auth_db.init_schema()` 僅在 Docker/VPS 部署透過 `migrate_auth_v1.py` 自動呼叫，桌面單機模式（`main.py`）從未呼叫，影響所有表（含新的 `credit_ledger`）——[[feedback_worktree_auth_db_never_initialized_on_fresh_env_2026-09-19]] 已記錄同類問題。
