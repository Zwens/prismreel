# DeeVid Quality V4.7 整合 + 月度點數額度設計

> 狀態：待使用者審閱
> 日期：2026-09-21
> 範圍：`prismreel.soulo-ai.com`（Docker Compose 部署版）與 desktop 單機模式共用同一套 provider/catalog 程式碼

## 1. 背景與目標

使用者有一組 DeeVid（`api.deevid.ai`）API key，訂閱方案每月 600 點，於每月 20 號重置。目標是把 DeeVid 的 `Quality V4.7` model 接進 Prismreel 現有的多 provider 影片生成架構（與 Seedance/Kling/Vidu 並列），並新增一個月度點數額度追蹤機制：記錄已用點數、顯示剩餘額度、額度用盡時硬擋生成請求直到下個週期。

**已查證的關鍵限制**：DeeVid 官方 API（`GET /v1/open-api/usage`）只回傳呼叫次數統計（`totalCalls`/`successCalls`/`failedCalls`），**不提供**點數餘額或每次呼叫實際扣點的查詢端點。官方定價頁也未列出 model/解析度/秒數對應的扣點對照表。因此「已用點數」無法向 DeeVid 官方查證，只能由 Prismreel 自行依約定公式估算並記帳——若日後這個估算值與 DeeVid 後台實際扣點出現落差，需要人工核對調整，這是本設計已知且使用者接受的取捨。

## 2. 核心決策（已與使用者確認，2026-09-21 Task 2 動工前查證後修正）

**🔴 修正記錄**：原設計文字寫的 `"Quality V4.7"` 經 Task 2 動工前查證（`GET /v1/open-api/image-video/models` 實際 API 回應，非文件範例）**不存在於 DeeVid 系統**。使用者確認實際要接 `"Quality V4.0"`（`start_image` 分類，即 image-to-video）。`Quality V4.0` 的 `durationRange` 為 `[4, 15]`，非原假設的 1–30 秒，故 duration 上限與使用者提供的三點驗證線性關係（5s=20/15s=60/30s=120）中的 30s 一點已超出實際 model 上限，予以捨棄，僅保留 5s/15s 兩點驗證扣點公式，公式本身（`duration × 4`）不受影響。

| 決策點 | 選擇 | 理由 |
|---|---|---|
| 整合範圍 | 僅 `Quality V4.0`（原誤植為不存在的 `Quality V4.7`），僅 image-to-video（`start_image` 模式，一張圖+提示詞→影片） | 使用者明確表示不需要其他 DeeVid model 或 t2v；model 名稱經實際 API 查證修正 |
| 解析度 | 固定 720p | 使用者提供的扣點規則基準即為 720p；`Quality V4.0` 支援 480p/720p/1080p，720p 選擇不變 |
| 秒數範圍 | 4–15 秒（整數，`Quality V4.0` 的 `durationRange`） | 原假設 1–30 秒與實際 API `durationRange:[4,15]` 不符，經查證修正上限；下限亦收斂至 4 秒 |
| 扣點公式 | `duration_seconds × 4` | 使用者提供 5s=20點/15s=60點/30s=120點；30s 已超出 `Quality V4.0` 實際秒數上限（15秒），予以捨棄，僅用 5s/15s 兩點驗證線性關係，公式不變 |
| 額度總量 | 600 點 / 週期 | 對應 DeeVid Pro 方案月費點數 |
| 週期起訖 | 每月 20 日重置（例如 9/20～10/19 為一個週期） | 與使用者 DeeVid 訂閱扣款日一致 |
| 額度用盡行為 | 硬擋：後端直接拒絕新的 DeeVid 生成請求，回傳週期重置日期 | 使用者明確選擇，避免估算值與官方實際扣點落差導致帳戶被鎖 |
| 額度歸屬範圍 | 全域單一額度（不分 Prismreel 使用者帳號） | DeeVid API key 是團隊共用單一帳號，額度綁在 key 本身而非個別登入使用者 |
| API Key 存放 | `DEEVID_API_KEY` 環境變數，僅寫入 `.env`（本機）與 VPS `.env`（不進 git） | 沿用既有 `VIDU_API_KEY`/`ARK_API_KEY` 模式；[[feedback_memory_md_files_are_git_tracked_redact_keys_2026-09-17]] |

## 3. 現有架構調查結論

Prismreel 的影片生成是資料驅動的多 provider 架構，新增一個 provider 需要碰三層：

1. **Model catalog（YAML → 生成 JSON，驅動前端選單）**：`config/model_catalog/families/<provider>.yaml` 定義 model/mode/duration/params/UI 顯示位置；`python scripts/build_model_catalog.py` 產生 `config/model_catalog/generated/model_catalog.json`（後端讀）與前端對應 JSON；`python scripts/validate_model_catalog.py` 驗證 schema。
2. **Provider adapter（`VideoGenModel` 子類別）**：`src/models/<provider>.py`，實作 `generate(prompt, output_path, **kwargs) -> (path, duration)`。既有 `vidu.py` 是最接近的範本（submit → poll → download 骨架，走 HTTP task queue API，跟 DeeVid 的 `task/submit` + `task/status` 模式一致）。
3. **Dispatch 路由**：`src/apps/playground/service.py` 的 `_process_video_generation()` 依 `model_id` 字串前綴做 `if/elif` 分派到 `_generate_video_<provider>()` 方法，該方法呼叫對應 adapter 的 `generate()`，回傳的 `usage` dict 交給 `_record_video_usage()` 記錄成本。DeeVid 的額度檢查要嵌入這一層——在 `_generate_video_deevid()` 呼叫 `DeeVidModel.generate()` **之前**做額度檢查，不足額度時 raise，讓現有的 batch 迴圈錯誤收集機制（`failures` 陣列）自然把錯誤回報給前端，不需要新的錯誤處理路徑。

現有 `usage_events` 表（`src/apps/comic_gen/usage_repo.py`）是純累計統計（用於「我的用量」頁面顯示美元成本），**沒有週期重置概念**，不適合直接拿來做額度扣抵判斷，因此本設計新增獨立的 `credit_ledger` 表。

## 4. 資料模型

### 4.1 新增 SQLite 表 `credit_ledger`（`output/auth.db`，沿用 `auth_db.py` 既有連線）

```sql
CREATE TABLE IF NOT EXISTS credit_ledger (
    id TEXT PRIMARY KEY,          -- uuid4 hex
    provider TEXT NOT NULL,       -- 'deevid'，預留未來其他 provider 額度沿用同一張表
    points INTEGER NOT NULL,      -- 本次扣抵點數（duration * 4）
    duration INTEGER NOT NULL,    -- 本次生成秒數，供稽核回推公式
    task_id TEXT,                 -- DeeVid 回傳的 taskId，供日後對照官方後台核實用
    created_at REAL NOT NULL
);
```

採**逐筆記錄 + 查詢時加總**（而非維護一個可變的「當期已用點數」欄位），理由：
- 與現有 `usage_events` 的稽核風格一致（保留完整歷史，可回溯每一筆的公式輸入）
- 避免併發寫入時的競態條件（多個生成請求同時扣抵，累加欄位需要鎖，逐筆插入+加總查詢天然安全）
- 額度不足判斷時，查詢當前週期內所有 `credit_ledger` 列的 `SUM(points)`，與 600 比較即可，資料量小（每月至多幾百筆）效能無虞

### 4.2 週期計算邏輯

```python
def current_period(now: float) -> tuple[float, float]:
    """回傳 (period_start_ts, period_end_ts)，以每月 20 日為錨點。
    今天若 >= 20 號，週期為本月20日 ~ 下月19日 23:59:59；
    今天若 < 20 號，週期為上月20日 ~ 本月19日 23:59:59。
    """
```

放在新檔 `src/apps/comic_gen/credit_ledger.py`（比照 `usage_repo.py` 的獨立模組風格），純函式易於單元測試，不依賴資料庫連線。

## 5. Provider Adapter：`src/models/deevid.py`

**已於 Task 2 動工前查證完成（`GET /v1/open-api/image-video/models` 實際 API 回應）**，三步驟流程（非原假設的單步驟）：

```
DeeVidModel(VideoGenModel)
  .generate(prompt, output_path, img_url=None, img_path=None, duration=5, **kwargs)
    1. 解析輸入圖片 URL：走既有 resolve_media_input()（OSS 簽名 URL，同 vidu.py 模式）。
    2. POST https://api.deevid.ai/v1/open-api/file-upload/upload/image
       （multipart/form-data，欄位 file=<圖片二進位>）
       回應：{"success": true, "data": {"userImageId": <int>, "imageUrl": <str>}}
       → 取得 userImageId，供下一步使用。
    3. POST https://api.deevid.ai/v1/open-api/image-video/start-image/task/submit
       body: {"model": "Quality V4.0", "prompt": ..., "userImageId": <int>,
              "resolution": "720p", "duration": <int 4-15>}
       （端點路徑、欄位名稱、model 名稱、duration 範圍皆已於 2026-09-21
        實際呼叫 DeeVid 帳號 API 查證，非文件範例推測）
    4. 輪詢 GET /v1/open-api/task/status?taskId=<id>，比照 vidu.py 的
       poll_interval=10s / max_wait=600s 節奏。
    5. status=SUCCESS 時下載 resultVideoUrl 存到 output_path。
    6. 回傳 (output_path, generation_time)。
```

**已查證確認的事項**（2026-09-21，實際呼叫 `GET /v1/open-api/image-video/models`）：
- image-to-video 對應 `start_image` 分類，端點為 `POST /image-video/start-image/task/submit`
- 圖片輸入非直接傳 URL，需先呼叫 `POST /file-upload/upload/image` 上傳取得 `userImageId`（number），再用該 ID 提交任務
- `Quality V4.0` 的 `durationRange` 為 `[4, 15]`（非原假設 1–30），且 `supportedDurations` 列出 5/10 為建議檔位，但 `durationRange` 存在代表接受此範圍內任意整數（比照既有 vidu.py 對 duration 的處理方式，不額外限制檔位，僅做上下限 clamp）
- 錯誤回應格式：文件範例與 submit/status 回應皆為 `{"success": bool, "data": {...}}`；失敗時觀察 HTTP status code 非 200 或 `success: false`（實際失敗案例的 message 欄位格式待 Task 2 實作時以真實錯誤呼叫二次確認，非阻塞項——沿用既有 provider adapter 對非 200 直接 raise 的慣例即可覆蓋）

## 6. 額度檢查與扣抵時機

```
_generate_video_deevid(gen, out_path):
    1. remaining = get_remaining_credits()  # 600 - SUM(points) in current period
    2. estimated_cost = gen.parameters["duration"] * 4
    3. if estimated_cost > remaining:
           raise DeeVidQuotaExceededError(remaining, period_end)
           → service.py 既有 failures 收集機制捕捉，前端顯示「額度不足，剩 X 點，Y 天後重置」
    4. DeeVidModel.generate(...)  # 呼叫成功才進入下一步
    5. record_credit_usage(provider="deevid", points=estimated_cost,
                            duration=duration, task_id=used_task_id)
```

扣抵發生在生成**成功**之後，不是送出請求時就扣——避免 DeeVid 端失敗（如真人偵測擋下）卻仍占用額度的情況，這與 `usage_events` 現有「僅記錄實際發生的呼叫」慣例一致。

## 7. API 端點

新增 `GET /usage/deevid-credits`（`api.py`，複用 `auth.require_login` 門禁）：

```json
{
  "used": 84,
  "remaining": 516,
  "total": 600,
  "period_start": "2026-09-20",
  "period_end": "2026-10-19"
}
```

## 8. 前端

1. **Model catalog YAML**（`config/model_catalog/families/deevid.yaml`）：單一 model 條目 `deevid/quality-v4.7`，`modes.i2v`，`duration: {type: slider, min: 1, max: 30, step: 1, default: 5}`，`visible_in: [video_sidebar]`（比照 Vidu 的 UI 顯示位置設定），驅動 `VideoGenPage` 的 model 選單自動出現這個選項，不需要額外手改前端 model 清單元件。
2. **用量頁**（`frontend/src/app/usage/page.tsx`）新增一張「DeeVid 額度」卡片：呼叫新的 `getDeeVidCredits()` API，顯示 `已用 X / 600 點（剩 Y，Z 天後重置）`的進度條。
3. **生成流程的額度用盡提示**：`_generate_video_deevid` 失敗訊息透過既有錯誤回報路徑（`failures` → 前端 toast）自然顯示，不需要在 model 選單本身做「用盡時置灰」這種主動預判——避免前端快取的剩餘額度與後端真實值不同步造成誤判，讓後端在生成當下做唯一真相判斷。

## 9. 測試與驗收（比照現有 L2 驗收等級：多檔修改需完整驗證）

1. `python scripts/validate_model_catalog.py` 通過（YAML schema 正確）
2. 週期計算函式（`current_period`）寫單元測試：涵蓋月初/月中/跨年邊界（12月20日→次年1月19日）
3. 額度扣抵/查詢邏輯寫單元測試：模擬多筆 `credit_ledger` 記錄，驗證 `SUM` 只計入當前週期範圍
4. 真實 DeeVid API 呼叫：至少一次 5 秒 i2v 生成成功，確認影片下載正常、`credit_ledger` 寫入 20 點、`/usage/deevid-credits` 回傳正確剩餘額度
5. 額度不足情境：手動在 `credit_ledger` insert 假資料頂到接近 600，確認下一次生成被正確拒絕且錯誤訊息含重置日期
6. 瀏覽器截圖驗證用量頁卡片正確顯示

## 10. 不在本次範圍內

- 不做其他 DeeVid model（僅 Quality V4.7）
- 不做 t2v/v2v（僅 i2v）
- 不做分使用者的額度拆分（額度綁在 API key 本身）
- 不嘗試對接 DeeVid 官方後台核實實際扣點（官方無此 API），估算落差由使用者自行定期人工核對 DeeVid 網頁後台用量後告知調整
