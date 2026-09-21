# DeeVid Quality V4.0 + 月度點數額度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 Prismreel 的影片生成頁能選用 DeeVid `Quality V4.0`（僅 image-to-video，720p，4-15 秒），並追蹤一個 600 點/週期（每月 20 日重置）的點數額度，額度用盡時後端硬擋新的 DeeVid 生成請求。

**Architecture:** 比照既有 `ViduModel`/`KlingModel` 的 provider adapter 模式（submit → poll → download），新增 `src/models/deevid.py`；額度記帳走新的獨立 SQLite 表 `credit_ledger`（逐筆記錄 + 查詢時加總，不對 `usage_events` 做侵入式修改）；model catalog 用 YAML 驅動前端選單。

**Tech Stack:** Python (FastAPI 後端), TypeScript/React (Next.js 前端), SQLite, pytest, requests

**Spec:** `docs/superpowers/specs/2026-09-21-deevid-quality-v4-7-credit-quota-design.md`

## Global Constraints

**🔴 2026-09-21 Task 2 動工前查證修正**：原計畫文字的 `"Quality V4.7"` 經實際呼叫 `GET /v1/open-api/image-video/models` 確認**不存在於 DeeVid 系統**（非版本延遲問題，是名稱不存在）。使用者確認改用 `"Quality V4.0"`，其 `durationRange` 為 `[4,15]`，非原假設 1–30。以下 Global Constraints 已更新為查證後的正確值，本檔案內下方各任務敘述若仍出現 `Quality V4.7` 或 duration 上限 30，以本節為準（已批量修正，若有殘留視為文件缺陷）。

- Model 字串固定為 `"Quality V4.0"`（原誤植不存在的 `"Quality V4.7"`），僅此一個 model，僅支援 image-to-video 模式（DeeVid `start_image` 分類）
- 解析度固定 `720p`，秒數範圍整數 **4–15**（`Quality V4.0` 的 `durationRange`，非原假設的 1–30）
- 圖片輸入為**兩步驟**：先 `POST /file-upload/upload/image` 上傳取得 `userImageId`，再用 `userImageId`（非圖片 URL）提交生成任務
- 扣點公式：`points = duration_seconds * 4`（使用者提供 5s=20/15s=60 兩點驗證線性關係；原第三點 30s=120 已超出 `Quality V4.0` 實際 duration 上限 15 秒，予以捨棄，公式本身不變）
- 額度總量 600 點/週期，週期以每月 20 日為錨點（今天 >= 20 號時，週期為「本月20日 00:00:00 ～ 下月19日 23:59:59」；今天 < 20 號時，週期為「上月20日 00:00:00 ～ 本月19日 23:59:59」）
- 額度用盡時後端**硬擋**：直接 raise，不允許呼叫 DeeVid API
- `DEEVID_API_KEY` 只寫入 `.env`／VPS `.env`，絕不寫入任何會進 git 版控的檔案（程式碼、memory、commit message、測試 fixture 一律用假值如 `"test-key"`）
- image-to-video 端點路徑、欄位名稱、model 清單、duration 範圍已於 2026-09-21 實際呼叫 DeeVid 帳號 API 查證完成（見上方修正說明），不再是 Task 2 的阻塞項
- 扣抵記帳時機：DeeVid 生成**成功**之後才寫入 `credit_ledger`，失敗（含真人偵測拒絕等）不消耗額度

---

### Task 1: `credit_ledger` 資料表與週期計算邏輯

**Files:**
- Modify: `src/apps/comic_gen/auth_db.py`（`init_schema()` 內新增 `CREATE TABLE IF NOT EXISTS credit_ledger`）
- Create: `src/apps/comic_gen/credit_ledger.py`
- Create: `src/apps/comic_gen/test_credit_ledger.py`

**Interfaces:**
- Consumes: `src.apps.comic_gen.auth_db.get_connection() -> sqlite3.Connection`（既有函式，`row_factory = sqlite3.Row`）
- Produces（後續 Task 3、Task 4 會用到）：
  - `credit_ledger.current_period(now_ts: float) -> tuple[float, float]` — 回傳 `(period_start_ts, period_end_ts)`
  - `credit_ledger.get_remaining_points(now_ts: float | None = None) -> int` — 回傳 `600 - 當前週期已用點數`（不會回傳負數以下才 clamp，允許回傳 0 或正整數；若已超額則回傳 0）
  - `credit_ledger.record_usage(points: int, duration: int, task_id: str | None) -> None` — 寫入一筆 `credit_ledger` 記錄，`created_at` 用 `time.time()`
  - `credit_ledger.PERIOD_ANCHOR_DAY = 20`（模組常數，供測試與後續程式碼引用同一個錨點日，不重複寫死 `20` 這個魔術數字）
  - `credit_ledger.TOTAL_POINTS_PER_PERIOD = 600`

- [ ] **Step 1: 在 `auth_db.py` 新增 `credit_ledger` 表**

在 `init_schema()` 函式內，緊接著既有 `usage_events` 的 `ALTER TABLE` 區塊之後（`auth_db.py:69` 附近的 `conn.commit()` 之前）新增：

```python
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_ledger (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                points INTEGER NOT NULL,
                duration INTEGER NOT NULL,
                task_id TEXT,
                created_at REAL NOT NULL
            )
            """
        )
```

放在 `conn.commit()` 呼叫之前，讓它跟其他 `CREATE TABLE` 一起在同一次 commit 內生效。

- [ ] **Step 2: 寫 `credit_ledger.py` 的失敗測試**

建立 `src/apps/comic_gen/test_credit_ledger.py`：

```python
import time
import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    import importlib
    from src.apps.comic_gen import auth_db, credit_ledger
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(credit_ledger)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def _ts(year, month, day, hour=12):
    import datetime
    return datetime.datetime(year, month, day, hour, tzinfo=datetime.timezone.utc).timestamp()


def test_current_period_on_or_after_anchor_day():
    from src.apps.comic_gen import credit_ledger

    # 2026-09-25 落在 9/20 ~ 10/19 週期內
    start, end = credit_ledger.current_period(_ts(2026, 9, 25))
    assert start == _ts(2026, 9, 20, hour=0)
    expected_end = _ts(2026, 10, 20, hour=0) - 1
    assert abs(end - expected_end) < 2  # 允許次秒誤差


def test_current_period_before_anchor_day():
    from src.apps.comic_gen import credit_ledger

    # 2026-09-05 落在上月(8/20) ~ 本月(9/19) 週期內
    start, end = credit_ledger.current_period(_ts(2026, 9, 5))
    assert start == _ts(2026, 8, 20, hour=0)
    expected_end = _ts(2026, 9, 20, hour=0) - 1
    assert abs(end - expected_end) < 2


def test_current_period_crosses_year_boundary():
    from src.apps.comic_gen import credit_ledger

    # 2027-01-05 落在 2026-12-20 ~ 2027-01-19 週期內
    start, end = credit_ledger.current_period(_ts(2027, 1, 5))
    assert start == _ts(2026, 12, 20, hour=0)


def test_get_remaining_points_starts_full():
    from src.apps.comic_gen import credit_ledger

    assert credit_ledger.get_remaining_points(_ts(2026, 9, 25)) == 600


def test_record_usage_reduces_remaining():
    from src.apps.comic_gen import credit_ledger

    now = _ts(2026, 9, 25)
    credit_ledger.record_usage(points=20, duration=5, task_id="task-1")
    assert credit_ledger.get_remaining_points(now) == 580


def test_record_usage_outside_current_period_not_counted():
    from src.apps.comic_gen import credit_ledger, auth_db
    import uuid

    # 手动插入一笔属于「上一个周期」的记录（created_at 落在 8/25），
    # 確認 get_remaining_points 只加總「當前週期」範圍內的點數。
    conn = auth_db.get_connection()
    conn.execute(
        "INSERT INTO credit_ledger (id, provider, points, duration, task_id, created_at) "
        "VALUES (?, 'deevid', 100, 25, 'old-task', ?)",
        (str(uuid.uuid4()), _ts(2026, 8, 25)),
    )
    conn.commit()
    conn.close()

    assert credit_ledger.get_remaining_points(_ts(2026, 9, 25)) == 600


def test_get_remaining_points_never_negative():
    from src.apps.comic_gen import credit_ledger

    now = _ts(2026, 9, 25)
    for _ in range(31):
        credit_ledger.record_usage(points=20, duration=5, task_id=None)
    # 31 * 20 = 620 > 600，應 clamp 為 0 而非負數
    assert credit_ledger.get_remaining_points(now) == 0
```

- [ ] **Step 3: 執行測試確認全部失敗（模組尚不存在）**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python -m pytest src/apps/comic_gen/test_credit_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.apps.comic_gen.credit_ledger'`

- [ ] **Step 4: 實作 `credit_ledger.py`**

```python
import calendar
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from .auth_db import get_connection

PERIOD_ANCHOR_DAY = 20
TOTAL_POINTS_PER_PERIOD = 600


def current_period(now_ts: Optional[float] = None) -> Tuple[float, float]:
    """Return (period_start_ts, period_end_ts) anchored on the 20th of each month.

    If today's day-of-month >= PERIOD_ANCHOR_DAY, the period runs from this
    month's 20th through the day before next month's 20th. Otherwise it runs
    from last month's 20th through the day before this month's 20th.
    """
    now_ts = time.time() if now_ts is None else now_ts
    now = datetime.fromtimestamp(now_ts, tz=timezone.utc)

    if now.day >= PERIOD_ANCHOR_DAY:
        start_year, start_month = now.year, now.month
    else:
        start_month = now.month - 1
        start_year = now.year
        if start_month == 0:
            start_month = 12
            start_year -= 1

    period_start = datetime(start_year, start_month, PERIOD_ANCHOR_DAY, tzinfo=timezone.utc)

    end_month = start_month + 1
    end_year = start_year
    if end_month == 13:
        end_month = 1
        end_year += 1
    period_end_exclusive = datetime(end_year, end_month, PERIOD_ANCHOR_DAY, tzinfo=timezone.utc)

    return period_start.timestamp(), period_end_exclusive.timestamp() - 1


def get_remaining_points(now_ts: Optional[float] = None) -> int:
    """600 minus points already used in the current period, clamped to >= 0."""
    now_ts = time.time() if now_ts is None else now_ts
    start, end = current_period(now_ts)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(points), 0) AS total FROM credit_ledger "
            "WHERE provider = 'deevid' AND created_at >= ? AND created_at <= ?",
            (start, end),
        ).fetchone()
        used = row["total"] or 0
    finally:
        conn.close()

    return max(0, TOTAL_POINTS_PER_PERIOD - used)


def record_usage(points: int, duration: int, task_id: Optional[str]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO credit_ledger (id, provider, points, duration, task_id, created_at) "
            "VALUES (?, 'deevid', ?, ?, ?, ?)",
            (str(uuid.uuid4()), points, duration, task_id, time.time()),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 5: 執行測試確認全部通過**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python -m pytest src/apps/comic_gen/test_credit_ledger.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add src/apps/comic_gen/auth_db.py src/apps/comic_gen/credit_ledger.py src/apps/comic_gen/test_credit_ledger.py
git commit -m "feat(credits): add credit_ledger table and monthly period accounting

DeeVid quota tracking needs a cycle-reset ledger distinct from the
existing usage_events statistics table. Period anchors on the 20th
of each month per the user's DeeVid subscription billing date."
```

---

### Task 2: DeeVid Provider Adapter — image-to-video 端點確認 + `DeeVidModel`

**Files:**
- Modify: `src/utils/endpoints.py`（新增 `"DEEVID"` 到 `PROVIDER_DEFAULTS`）
- Modify: `.env.example`（新增 `DEEVID_API_KEY` 說明行）
- Create: `src/models/deevid.py`
- Create: `src/models/test_deevid.py`

**Interfaces:**
- Consumes:
  - `src.models.base.VideoGenModel`（抽象基底類別，`__init__(self, config: dict)`，`self.config = config`）
  - `src.utils.endpoints.get_provider_base_url(provider: str, default: str = None) -> str`
  - `src.utils.provider_media.resolve_media_input(ref, *, model_name, modality, backend, uploader) -> ResolvedMediaInput`（`.value` 是解析後的 URL 字串）— **此函式目前對 DeeVid 尚未支援，Task 3 會補上 dispatch 分支；Task 2 先寫好呼叫端，Task 2 的測試用 mock 繞過這個相依，不需要等 Task 3 完成才能跑測試**
  - `src.utils.oss_utils.OSSImageUploader`（`__init__()` 無參數）
- Produces（Task 4 的 `service.py` dispatch 會用到）：
  - `DeeVidModel(VideoGenModel)`
  - `DeeVidModel.generate(self, prompt: str, output_path: str, img_url: str = None, img_path: str = None, duration: int = 5, **kwargs) -> Tuple[str, float]` — 回傳 `(output_path, generation_time_seconds)`
  - `DeeVidModel.last_task_id: Optional[str]` — 實例屬性，`generate()` 執行後記錄最近一次 DeeVid `taskId`，供呼叫端寫入 `credit_ledger.record_usage()` 的 `task_id` 欄位

**✅ 動工前查證已完成（2026-09-21，實際呼叫 DeeVid 帳號 `GET /v1/open-api/image-video/models`，非文件範例推測）**：

- Model 名稱：原計畫 `"Quality V4.7"` 經查證**不存在**於系統，確認改用 `"Quality V4.0"`（`start_image` 分類，即 image-to-video）
- `durationRange`: `[4, 15]`（非原假設 1–30）
- 圖片輸入為**兩步驟**流程，非單一 URL 欄位：
  1. `POST /v1/open-api/file-upload/upload/image`（multipart，欄位 `file`）→ 回應 `{"success": true, "data": {"userImageId": <int>, "imageUrl": <str>}}`
  2. `POST /v1/open-api/image-video/start-image/task/submit`，body 含 `userImageId`（非 `image` URL）
- Status 查詢：`GET /v1/open-api/task/status?taskId=<id>`（與原假設一致）

- [ ] **Step 1: 確認結果已記錄如上，供以下步驟直接使用，不需重複查證**

已查證結果：
- Upload 端點：`POST {base_url}/file-upload/upload/image`
- Submit 端點：`POST {base_url}/image-video/start-image/task/submit`
- Body：`{"model": "Quality V4.0", "prompt": ..., "userImageId": <int>, "resolution": "720p", "duration": <int 4-15>}`
- Status 查詢：`GET {base_url}/task/status?taskId=<id>`

- [ ] **Step 2: 在 `endpoints.py` 註冊 DeeVid base URL**

```python
PROVIDER_DEFAULTS = {
    "GEMINI": "https://generativelanguage.googleapis.com",
    "KLING": "https://api-beijing.klingai.com/v1",
    "VIDU": "https://api.vidu.cn/ent/v2",
    "DEEVID": "https://api.deevid.ai/v1/open-api",
}
```

- [ ] **Step 3: 在 `.env.example` 新增說明行**

在既有 `VIDU_API_KEY` 區塊之後插入：

```
# DeeVid AI 配置 (可选，用于 DeeVid Quality V4.0 图生视频)
DEEVID_API_KEY=your_deevid_api_key_here
```

- [ ] **Step 4: 寫 `test_deevid.py` 的失敗測試（mock HTTP，不打真實 API）**

```python
from unittest.mock import patch, MagicMock


def test_submit_and_poll_success(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import DeeVidModel

    model = DeeVidModel({})

    upload_response = MagicMock()
    upload_response.status_code = 200
    upload_response.json.return_value = {
        "success": True,
        "data": {"userImageId": 123, "imageUrl": "https://cdn.deevid.ai/images/xxx.png"},
    }

    submit_response = MagicMock()
    submit_response.status_code = 200
    submit_response.json.return_value = {
        "success": True,
        "data": {"taskId": 10002, "status": "INIT"},
    }

    status_response = MagicMock()
    status_response.status_code = 200
    status_response.json.return_value = {
        "success": True,
        "data": {
            "taskId": 10002,
            "status": "SUCCESS",
            "resultVideoUrl": "https://cdn.deevid.ai/videos/xxx.mp4",
        },
    }

    video_bytes_response = MagicMock()
    video_bytes_response.content = b"fake-video-bytes"

    out_path = str(tmp_path / "out.mp4")

    with patch("src.models.deevid.requests.post", side_effect=[upload_response, submit_response]), \
         patch("src.models.deevid.requests.get", side_effect=[status_response, video_bytes_response]), \
         patch("src.models.deevid.time.sleep", return_value=None), \
         patch(
             "src.models.deevid.resolve_media_input",
             return_value=MagicMock(value="https://example.com/input.png"),
         ), \
         patch("src.models.deevid.open", create=True), \
         patch("src.models.deevid.requests.get") as mock_get:
        mock_get.side_effect = [status_response, video_bytes_response]
        # image bytes fetch for upload uses requests.get on the resolved URL first,
        # then poll status, then download result video — see Step 6 for exact call order
        result_path, elapsed = model.generate(
            prompt="a cat walking",
            output_path=out_path,
            img_url="https://example.com/input.png",
            duration=5,
        )

    assert result_path == out_path
    assert isinstance(elapsed, float)
    assert model.last_task_id == "10002"


def test_submit_failure_raises(monkeypatch):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import DeeVidModel

    model = DeeVidModel({})

    upload_response = MagicMock()
    upload_response.status_code = 200
    upload_response.json.return_value = {
        "success": True,
        "data": {"userImageId": 123, "imageUrl": "https://cdn.deevid.ai/images/xxx.png"},
    }

    submit_response = MagicMock()
    submit_response.status_code = 400
    submit_response.text = '{"success": false, "message": "bad request"}'

    with patch("src.models.deevid.requests.post", side_effect=[upload_response, submit_response]), \
         patch(
             "src.models.deevid.resolve_media_input",
             return_value=MagicMock(value="https://example.com/input.png"),
         ), \
         patch("src.models.deevid.requests.get") as mock_get:
        mock_get.return_value.content = b"fake-image-bytes"
        try:
            model.generate(
                prompt="x", output_path="/tmp/out.mp4",
                img_url="https://example.com/input.png", duration=5,
            )
            assert False, "should have raised"
        except RuntimeError as exc:
            assert "400" in str(exc)


def test_task_failed_status_raises(monkeypatch):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import DeeVidModel

    model = DeeVidModel({})

    upload_response = MagicMock()
    upload_response.status_code = 200
    upload_response.json.return_value = {
        "success": True,
        "data": {"userImageId": 123, "imageUrl": "https://cdn.deevid.ai/images/xxx.png"},
    }

    submit_response = MagicMock()
    submit_response.status_code = 200
    submit_response.json.return_value = {"success": True, "data": {"taskId": 1, "status": "INIT"}}

    status_response = MagicMock()
    status_response.status_code = 200
    status_response.json.return_value = {
        "success": True,
        "data": {"taskId": 1, "status": "FAILED"},
    }

    with patch("src.models.deevid.requests.post", side_effect=[upload_response, submit_response]), \
         patch("src.models.deevid.requests.get") as mock_get, \
         patch("src.models.deevid.time.sleep", return_value=None), \
         patch(
             "src.models.deevid.resolve_media_input",
             return_value=MagicMock(value="https://example.com/input.png"),
         ):
        mock_get.side_effect = [MagicMock(content=b"fake-image-bytes"), status_response]
        try:
            model.generate(
                prompt="x", output_path="/tmp/out.mp4",
                img_url="https://example.com/input.png", duration=5,
            )
            assert False, "should have raised"
        except RuntimeError as exc:
            assert "FAILED" in str(exc) or "failed" in str(exc)


def test_duration_clamped_to_supported_range(monkeypatch):
    """Quality V4.0 durationRange is [4,15] — values outside must clamp, not pass through raw."""
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import DeeVidModel, MIN_DURATION, MAX_DURATION

    assert MIN_DURATION == 4
    assert MAX_DURATION == 15
```

**注意給實作者**：上面 `test_submit_and_poll_success` 等測試裡的 mock 呼叫順序（`requests.post`/`requests.get` 的 `side_effect` 列表順序）必須跟 Step 6 `generate()` 實際的呼叫順序完全對應——`generate()` 內部呼叫順序是：(1) `requests.get` 抓取待上傳圖片的 bytes（若 `resolve_media_input` 回傳的是 URL 需要先下載才能 multipart 上傳）、(2) `requests.post` 上傳圖片拿 `userImageId`、(3) `requests.post` 提交生成任務、(4) `requests.get` 輪詢狀態、(5) `requests.get` 下載結果影片。若實作時發現這與測試 mock 順序兜不起來，以 Step 6 的真實程式碼呼叫順序為準，測試的 `side_effect` 列表順序跟著改，不要為了讓測試通過而扭曲實作順序。

- [ ] **Step 5: 執行測試確認全部失敗**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python -m pytest src/models/test_deevid.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.models.deevid'`

- [ ] **Step 6: 實作 `src/models/deevid.py`**

```python
"""DeeVid video generation model adapter.

API: https://api.deevid.ai/v1/open-api
Auth: Bearer token via DEEVID_API_KEY
Model: "Quality V4.0" only (image-to-video, "start_image" category)

Endpoints (confirmed 2026-09-21 against the account's own API via a real
GET /v1/open-api/image-video/models call — the original design's
"Quality V4.0" does not exist in DeeVid's system; see Task 2 Global
Constraints correction note in
docs/superpowers/plans/2026-09-21-deevid-quality-v4-7-credit-quota.md):
  upload -> POST /file-upload/upload/image (multipart, field "file") -> userImageId
  submit -> POST /image-video/start-image/task/submit (body uses userImageId, not a URL)
  status -> GET  /task/status?taskId=<id>
"""

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import requests

from .base import VideoGenModel
from ..utils.endpoints import get_provider_base_url
from ..utils.oss_utils import OSSImageUploader
from ..utils.provider_media import resolve_media_input

logger = logging.getLogger(__name__)

MODEL_NAME = "Quality V4.0"
RESOLUTION = "720p"
MIN_DURATION = 4
MAX_DURATION = 15


class DeeVidModel(VideoGenModel):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key") or os.getenv("DEEVID_API_KEY", "")
        self.last_task_id: Optional[str] = None

    def _headers(self, json_content: bool = True) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if json_content:
            headers["Content-Type"] = "application/json"
        return headers

    def _resolve_image_url(self, img_url: Optional[str], img_path: Optional[str]) -> str:
        ref = img_url if (isinstance(img_url, str) and img_url.startswith(("http://", "https://"))) else (img_path or img_url)
        if not ref:
            raise ValueError("DeeVid image-to-video requires img_path or img_url")
        resolved = resolve_media_input(
            ref,
            model_name="deevid/quality-v4.0",
            modality="image",
            backend="vendor",
            uploader=OSSImageUploader(),
        )
        return resolved.value

    def _upload_image(self, base_url: str, image_url: str) -> int:
        """Download the resolved image and re-upload it to DeeVid's own
        file-upload endpoint, returning the userImageId the submit API needs."""
        image_bytes = requests.get(image_url, timeout=60).content
        upload_url = f"{base_url}/file-upload/upload/image"
        resp = requests.post(
            upload_url,
            headers=self._headers(json_content=False),
            files={"file": ("input.png", image_bytes)},
            timeout=60,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"DeeVid image upload failed (HTTP {resp.status_code}): {resp.text}")
        data = resp.json()
        user_image_id = (data.get("data") or {}).get("userImageId")
        if user_image_id is None:
            raise RuntimeError(f"No userImageId in DeeVid upload response: {data}")
        return user_image_id

    def generate(
        self,
        prompt: str,
        output_path: str,
        img_url: str = None,
        img_path: str = None,
        duration: int = 5,
        **kwargs,
    ) -> Tuple[str, float]:
        duration = max(MIN_DURATION, min(MAX_DURATION, int(duration)))
        start_time = time.time()
        base_url = get_provider_base_url("DEEVID")

        image_url = self._resolve_image_url(img_url, img_path)
        user_image_id = self._upload_image(base_url, image_url)

        submit_url = f"{base_url}/image-video/start-image/task/submit"
        body = {
            "model": MODEL_NAME,
            "prompt": prompt or "",
            "userImageId": user_image_id,
            "resolution": RESOLUTION,
            "duration": duration,
        }
        logger.info("[DeeVid] Submitting i2v task (duration=%ss)", duration)
        resp = requests.post(submit_url, headers=self._headers(), json=body, timeout=30)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"DeeVid submission failed (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        task_id = str((data.get("data") or {}).get("taskId") or "")
        if not task_id:
            raise RuntimeError(f"No taskId in DeeVid response: {data}")
        self.last_task_id = task_id

        status_url = f"{base_url}/task/status"
        max_wait = 600
        poll_interval = 10
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                status_resp = requests.get(
                    status_url, headers=self._headers(),
                    params={"taskId": task_id}, timeout=30,
                )
            except requests.RequestException as exc:
                logger.warning("[DeeVid] Poll request failed (%s); retrying (task %s)", exc, task_id)
                continue

            if status_resp.status_code != 200:
                logger.warning("[DeeVid] Poll returned HTTP %s", status_resp.status_code)
                continue

            status_data = (status_resp.json().get("data")) or {}
            status = (status_data.get("status") or "").upper()
            logger.info("[DeeVid] Task %s status: %s (%ss)", task_id, status, elapsed)

            if status == "SUCCESS":
                video_url = status_data.get("resultVideoUrl")
                if not video_url:
                    raise RuntimeError(f"DeeVid task {task_id} succeeded but has no resultVideoUrl: {status_data}")
                video_content = requests.get(video_url, timeout=120).content
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(video_content)
                generation_time = time.time() - start_time
                logger.info("[DeeVid] Done in %.1fs -> %s", generation_time, output_path)
                return output_path, generation_time

            if status == "FAILED":
                raise RuntimeError(f"DeeVid task {task_id} failed: {status_data}")

        raise RuntimeError(f"DeeVid task {task_id} timed out after {max_wait}s")
```

**注意給實作者**：`_upload_image` 目前用 `requests.get(image_url).content` 重新下載 `resolve_media_input` 解析出來的 URL 內容再上傳——若 `resolve_media_input` 在本機路徑情境下已經能直接拿到本機檔案 bytes（不必先繞一圈 OSS URL 再下載回來），可以視情況優化，但這不是本任務的阻塞項，先以「無論輸入是本機路徑或 URL，統一先經過 resolve_media_input 取得一個可下載的 URL，再下載+重新上傳給 DeeVid」這個保守路徑跑通測試，效能優化留待日後有真實效能問題時再處理（YAGNI）。

- [ ] **Step 7: 執行測試確認全部通過**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python -m pytest src/models/test_deevid.py -v`
Expected: 4 passed

- [ ] **Step 8: Commit**

```bash
git add src/utils/endpoints.py .env.example src/models/deevid.py src/models/test_deevid.py
git commit -m "feat(deevid): add DeeVid Quality V4.0 image-to-video adapter

Submit/poll/download flow mirrors the existing ViduModel adapter, plus
a required image-upload step DeeVid's API needs before submit. Model
name and endpoint paths confirmed via a real GET /image-video/models
call — the design's original 'Quality V4.0' does not exist in DeeVid's
system; the account's actual usable models are V2.0/V2.5/V4.0 and the
Master series. duration range corrected to [4,15] to match Quality
V4.0's real durationRange (was assumed 1-30)."
```

---

### Task 3: `provider_media.py` 支援 DeeVid 圖片輸入 dispatch

**Files:**
- Modify: `src/utils/provider_media.py`（`_resolve_vendor_url_mode` 呼叫處新增 `deevid_vendor_` 分支）
- Modify: `src/utils/provider_registry.py`（`DEFAULT_PROVIDER_FAMILIES` 新增 deevid family，作為 catalog 載入失敗時的 fallback）
- Create: `src/utils/test_provider_media.py`（目前不存在，需新建）

**Interfaces:**
- Consumes: Task 2 產出的 `DeeVidModel`（本任務不直接呼叫它，但驗證 `resolve_media_input(model_name="deevid/quality-v4.0", modality="image", backend="vendor", ...)` 能正確路由，不再拋出 `Unsupported provider media input mode`）
- Produces: `resolve_media_input` 對 `model_name` 以 `"deevid"` 開頭的呼叫不再拋錯，行為與既有 `vidu_vendor_image_url` 分支一致（本機路徑 → OSS 上傳簽名 URL；已是 http(s) URL → 直接透傳）

**🔴 2026-09-21 Task 3 動工查證後修正（load-bearing plan defect，Task 3 implementer 動手前查證發現，控制端裁決）**：原 Step 1 的兩個測試都經由 `get_default_provider_registry()`（全域函式）驗證，但該函式的優先序是「`config/model_catalog/generated/model_catalog.json` 若能成功載入，直接用它建 registry，`DEFAULT_PROVIDER_FAMILIES` 只在 catalog 載入**拋例外**時才當 fallback」——已用程式碼追蹤+實際執行雙重驗證（`provider_registry.py:108-113` 的 `try/except` 只包住 catalog 載入本身，`get_family_config()` 查無 family 拋的 `KeyError` 是在 registry 已建好之後的查詢層錯誤，不會觸發 fallback）。目前 worktree 內 `model_catalog.json` 已存在且能成功載入（不含 deevid，因為 `deevid.yaml` 要到 Task 4 才建立），所以透過 `get_default_provider_registry()` 測試 `DEFAULT_PROVIDER_FAMILIES` 新增的 deevid entry，在 Task 4 完成前**必定失敗**，形成 Task 3 依賴 Task 4 才能通過的隱性順序，違反每個任務應獨立可驗證的原則。

**裁決**：`resolve_media_input()` 本身已支援可選的 `registry: Optional[ProviderRegistry] = None` 參數（`provider_media.py:170`，未使用時才 fallback 到 `get_default_provider_registry()`，見 `provider_media.py:181`）。改用這個既有注入點，直接建構一個只含 `DEFAULT_PROVIDER_FAMILIES`（含本任務新增的 deevid entry）的 `ProviderRegistry` 傳入測試呼叫，繞開「全域 registry 被 catalog JSON 覆蓋」的問題，讓 Task 3 只驗證「`DEFAULT_PROVIDER_FAMILIES` entry 本身 + dispatch 分支邏輯」這個本任務實際負責的範圍，不依賴 Task 4 是否已跑過 catalog 生成。Task 4 完成後，`get_default_provider_registry()` 的 catalog 路徑自然也會含 deevid（因為 catalog JSON 會被 Task 4 的 build 腳本重新生成含 `deevid.yaml`），兩個來源屆時保持一致，但那是 Task 4 自身該驗證的事，不需要 Task 3 的測試提前依賴它。

- [ ] **Step 1: 建立 `src/utils/test_provider_media.py`（目前不存在）**

```python
def test_resolve_media_input_deevid_passthrough_url():
    from src.utils.provider_media import resolve_media_input
    from src.utils.provider_registry import ProviderRegistry, DEFAULT_PROVIDER_FAMILIES

    fallback_registry = ProviderRegistry(DEFAULT_PROVIDER_FAMILIES)
    resolved = resolve_media_input(
        "https://example.com/photo.png",
        model_name="deevid/quality-v4.0",
        modality="image",
        backend="vendor",
        uploader=None,
        registry=fallback_registry,
    )
    assert resolved.value == "https://example.com/photo.png"


def test_deevid_family_registered_in_default_provider_families():
    """驗證本任務新增的 DEFAULT_PROVIDER_FAMILIES deevid entry 本身正確——
    刻意繞開 get_default_provider_registry()，因為那個函式在 catalog JSON
    載入成功時會直接用 catalog 建 registry（不含 deevid，要到 Task 4 建立
    deevid.yaml 並重新生成 catalog 後才會有），不會走到這個 fallback tuple。
    這裡改為直接用 DEFAULT_PROVIDER_FAMILIES 建一個獨立 registry 來驗證
    entry 本身，讓本測試不依賴 Task 4 是否已完成。"""
    from src.utils.provider_registry import ProviderRegistry, DEFAULT_PROVIDER_FAMILIES

    registry = ProviderRegistry(DEFAULT_PROVIDER_FAMILIES)
    config = registry.get_family_config("deevid/quality-v4.0")
    assert config.model_family == "deevid"
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python -m pytest src/utils/test_provider_media.py -k deevid -v`
Expected: FAIL — `KeyError: No provider family registered for model 'deevid/quality-v4.0'`（兩個測試都因 `DEFAULT_PROVIDER_FAMILIES` 尚未含 deevid entry 而失敗）

- [ ] **Step 3: 在 `provider_registry.py` 註冊 deevid family**

在 `DEFAULT_PROVIDER_FAMILIES` tuple 內新增（跟 `vidu` 條目同層級）：

```python
    ProviderFamilyConfig(
        model_family="deevid",
        backend_default="vendor",
        credential_sources={"vendor": ("DEEVID_API_KEY",)},
        supported_modalities=("i2v",),
        image_input_mode={"vendor": "deevid_vendor_image_url"},
        audio_input_mode={},
        reference_video_input_mode={},
    ),
```

- [ ] **Step 4: 在 `provider_media.py` 的 `_resolve_vendor_url_mode` dispatch 新增分支**

修改 `resolve_media_input()` 內原本這段（約在 `provider_media.py:199-220`）：

```python
    if (
        mode.startswith("vidu_vendor_")
        or mode.startswith("kling_vendor_")
        or mode.startswith("pixverse_vendor_")
        or mode.startswith("byteplus_ark_")
    ):
        if mode.startswith("vidu_vendor_"):
            provider_label = "Vidu"
        elif mode.startswith("kling_vendor_"):
            provider_label = "Kling"
        elif mode.startswith("pixverse_vendor_"):
            provider_label = "Pixverse"
        else:
            provider_label = "BytePlus"
```

改為：

```python
    if (
        mode.startswith("vidu_vendor_")
        or mode.startswith("kling_vendor_")
        or mode.startswith("pixverse_vendor_")
        or mode.startswith("byteplus_ark_")
        or mode.startswith("deevid_vendor_")
    ):
        if mode.startswith("vidu_vendor_"):
            provider_label = "Vidu"
        elif mode.startswith("kling_vendor_"):
            provider_label = "Kling"
        elif mode.startswith("pixverse_vendor_"):
            provider_label = "Pixverse"
        elif mode.startswith("deevid_vendor_"):
            provider_label = "DeeVid"
        else:
            provider_label = "BytePlus"
```

- [ ] **Step 5: 執行測試確認通過**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python -m pytest src/utils/test_provider_media.py -k deevid -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add src/utils/provider_media.py src/utils/provider_registry.py src/utils/test_provider_media.py
git commit -m "feat(deevid): register deevid provider family for media resolution

resolve_media_input() previously raised 'Unsupported provider media
input mode' for any deevid/* model id. Adds the vendor image_input_mode
dispatch branch alongside the existing vidu/kling/pixverse/byteplus ones."
```

---

### Task 4: Model Catalog YAML + 生成 + Schema 驗證

**Files:**
- Create: `config/model_catalog/families/deevid.yaml`
- Modify: 無（`config/model_catalog/generated/model_catalog.json` 由腳本自動產生，不手動編輯）

**Interfaces:**
- Consumes: `config/model_catalog/schema/model-catalog.schema.json`（既有 schema，本任務不修改，只需符合它）
- Produces: `deevid/quality-v4.0` model id，`modes.i2v`，供 Task 5 的前端與 Task 6 的 dispatch 路由使用

- [ ] **Step 1: 建立 `config/model_catalog/families/deevid.yaml`**

比照 `vidu.yaml` 的結構，但只有一個 model、一個 mode：

```yaml
family: deevid
display_name: DeeVid
provider: deevid
routing_prefixes:
  - deevid
supported_backends:
  - vendor
default_backend: vendor
credential_sources:
  vendor:
    - DEEVID_API_KEY
supported_modalities:
  - i2v
transport:
  image_input_mode:
    vendor: deevid_vendor_image_url
  audio_input_mode: {}
  reference_video_input_mode: {}
docs:
  official_snapshot_ids:
    - deevid/2026-09-21
models:
  - id: deevid/quality-v4.0
    display_name: DeeVid Quality V4.0
    description: "DeeVid Quality V4.0 — image-to-video, 720p fixed, 600 credits/cycle quota (resets on the 20th)"
    status: active
    release_stage: stable
    runtime:
      vendor:
        gateway: deevid
        api_model_id: "Quality V4.0"
    docs:
      context_hub_doc_ids:
        - deevid/vendor-api
    modes:
      i2v:
        legacy_id: deevid-quality-v4-7-i2v
        display_name: DeeVid Quality V4.0 I2V
        description: Image-to-video with a monthly credit quota (600 pts, resets on the 20th)
        capabilities: [i2v]
        runtime:
        ui:
          selection_group: i2v
          visible_in: [video_sidebar]
          order: 80
          badges: [new]
        duration:
          type: slider
          min: 4
          max: 15
          step: 1
          default: 5
        params:
          resolution:
            options: [720p]
            default: 720p
          seed: false
          negativePrompt: false
          promptExtend: false
          watermark: false
        inputs:
          reference_images:
            max: 1
            reference_type: image
```

- [ ] **Step 2: 產生 catalog JSON**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python scripts/build_model_catalog.py`
Expected: 印出三行 `Wrote ... to ...`，無例外

- [ ] **Step 3: 驗證 schema**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python scripts/validate_model_catalog.py`
Expected: 驗證通過（無 schema violation 輸出；若失敗，依錯誤訊息調整 Step 1 的 YAML 欄位，schema 檔案是唯一真相來源，不得略過驗證直接進下一步）

- [ ] **Step 4: 確認 `resolve_provider_backend` 能正確解析新 model**

Run:
```bash
cd "AI 短片系統 Prismreel" && .venv/Scripts/python -c "
from src.utils.provider_registry import get_default_provider_registry
r = get_default_provider_registry()
print(r.resolve_backend('deevid/quality-v4.0'))
"
```
Expected: 輸出 `vendor`

- [ ] **Step 5: Commit（含自動生成的 catalog JSON）**

```bash
git add config/model_catalog/families/deevid.yaml config/model_catalog/generated/model_catalog.json
git status --short  # 確認前端 generated JSON 路徑是否也被 build 腳本改動，一併加入
git add -A config/model_catalog/
git commit -m "feat(deevid): register Quality V4.0 in the model catalog

Single i2v mode, 720p fixed, 4-15s duration slider (Quality V4.0's real durationRange). Drives the video
generation sidebar's model dropdown without frontend code changes."
```

---

### Task 5: 額度檢查整合進生成流程

**Files:**
- Modify: `src/apps/playground/service.py`（新增 `_generate_video_deevid()` 方法 + `_process_video_generation()` dispatch 分支）
- Test: `src/apps/playground/test_service_deevid.py`

**Interfaces:**
- Consumes:
  - Task 1: `credit_ledger.get_remaining_points(now_ts=None) -> int`, `credit_ledger.record_usage(points, duration, task_id) -> None`
  - Task 2: `DeeVidModel(config).generate(prompt, output_path, img_url, img_path, duration, **kwargs) -> (path, float)`, `DeeVidModel.last_task_id: Optional[str]`
  - 既有: `PlaygroundService._resolve_first_input_media(gen) -> (img_path, img_url)`
- Produces: `_generate_video_deevid(self, gen: PlaygroundGeneration, out_path: str) -> Optional[dict]` — 回傳 `{"provider": "deevid", "duration": <int>, "resolution": "720p"}` 供 `_record_video_usage` 記錄美元成本統計（DeeVid 無公開定價換算美元，此處 `cost_usd` 會是 `None`，這是預期行為，不需額外處理）

- [ ] **Step 1: 寫失敗測試**

```python
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    import importlib
    from src.apps.comic_gen import auth_db, credit_ledger
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(credit_ledger)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def _make_service():
    from src.apps.playground.service import PlaygroundService
    from src.apps.playground.storage import PlaygroundStorage
    storage = MagicMock(spec=PlaygroundStorage)
    return PlaygroundService(storage)


def _make_gen(duration=5):
    from src.apps.playground.models import PlaygroundGeneration, PlaygroundMode
    return PlaygroundGeneration(
        id="gen-1", mode=PlaygroundMode.I2V, model_id="deevid/quality-v4.0",
        prompt="test", input_media=["https://example.com/in.png"],
        parameters={"duration": duration}, created_at="2026-09-21T00:00:00Z",
    )


def test_generate_video_deevid_success_records_usage():
    service = _make_service()
    gen = _make_gen(duration=5)

    fake_model = MagicMock()
    fake_model.generate.return_value = ("/tmp/out.mp4", 12.3)
    fake_model.last_task_id = "task-99"

    with patch("src.models.deevid.DeeVidModel", return_value=fake_model):
        usage = service._generate_video_deevid(gen, "/tmp/out.mp4")

    assert usage == {"provider": "deevid", "duration": 5, "resolution": "720p"}

    from src.apps.comic_gen import credit_ledger
    assert credit_ledger.get_remaining_points() == 580  # 600 - 5*4


def test_generate_video_deevid_blocks_when_quota_exhausted():
    from src.apps.comic_gen import credit_ledger

    for _ in range(30):
        credit_ledger.record_usage(points=20, duration=5, task_id=None)
    # 30 * 20 = 600, remaining = 0

    service = _make_service()
    gen = _make_gen(duration=5)

    with pytest.raises(RuntimeError) as exc_info:
        service._generate_video_deevid(gen, "/tmp/out.mp4")

    assert "額度" in str(exc_info.value) or "quota" in str(exc_info.value).lower()


def test_generate_video_deevid_failure_does_not_consume_quota():
    service = _make_service()
    gen = _make_gen(duration=5)

    fake_model = MagicMock()
    fake_model.generate.side_effect = RuntimeError("DeeVid task failed: content policy")

    from src.apps.comic_gen import credit_ledger

    with patch("src.models.deevid.DeeVidModel", return_value=fake_model):
        with pytest.raises(RuntimeError):
            service._generate_video_deevid(gen, "/tmp/out.mp4")

    assert credit_ledger.get_remaining_points() == 600  # 未扣點


def test_process_video_generation_routes_deevid_model_id():
    service = _make_service()
    gen = _make_gen(duration=5)

    with patch.object(service, "_generate_video_deevid", return_value=None) as mock_deevid, \
         patch.object(service, "_extract_video_thumbnail", return_value=None):
        service._process_video_generation(gen)

    mock_deevid.assert_called_once()
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python -m pytest src/apps/playground/test_service_deevid.py -v`
Expected: FAIL — `AttributeError: 'PlaygroundService' object has no attribute '_generate_video_deevid'`

- [ ] **Step 3: 在 `service.py` 新增 dispatch 分支**

修改 `_process_video_generation()`（`service.py:319-329`）：

```python
                if model_lower.startswith("seedance"):
                    usage = self._generate_video_seedance(gen, out_path)
                elif model_lower.startswith("kling"):
                    usage = self._generate_video_kling(gen, out_path)
                elif model_lower.startswith("vidu") or model_lower.startswith("viduq"):
                    usage = self._generate_video_vidu(gen, out_path)
                elif model_lower.startswith("deevid"):
                    usage = self._generate_video_deevid(gen, out_path)
                else:
                    # happyhorse / pixverse 随 DashScope 下线，专属分支已移除；
                    # 未识别的 id 一并落到 Seedance 兜底。
                    usage = self._generate_video_default(gen, out_path)
```

- [ ] **Step 4: 新增 `_generate_video_deevid` 方法**

緊接在既有 `_generate_video_vidu` 方法之後（`service.py:590` 附近）新增：

```python
    def _generate_video_deevid(self, gen: PlaygroundGeneration, out_path: str) -> Optional[dict]:
        """Delegate to :class:`DeeVidModel`, enforcing the monthly credit quota
        before spending it on an API call."""
        from ...apps.comic_gen import credit_ledger
        from ...models.deevid import DeeVidModel

        params = gen.parameters
        duration = int(params.get("duration", 5))
        estimated_points = duration * 4

        remaining = credit_ledger.get_remaining_points()
        if estimated_points > remaining:
            _, period_end = credit_ledger.current_period()
            from datetime import datetime, timezone
            reset_date = datetime.fromtimestamp(period_end + 1, tz=timezone.utc).strftime("%Y-%m-%d")
            raise RuntimeError(
                f"DeeVid 額度不足：本次需要 {estimated_points} 點，剩餘 {remaining} 點，"
                f"將於 {reset_date} 重置"
            )

        img_path, img_url = self._resolve_first_input_media(gen)

        model = DeeVidModel({})
        model.generate(
            prompt=gen.prompt,
            output_path=out_path,
            img_url=img_url,
            img_path=img_path,
            duration=duration,
        )

        credit_ledger.record_usage(
            points=estimated_points, duration=duration, task_id=model.last_task_id,
        )

        return {"provider": "deevid", "duration": duration, "resolution": "720p"}
```

- [ ] **Step 5: 執行測試確認全部通過**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python -m pytest src/apps/playground/test_service_deevid.py -v`
Expected: 4 passed

- [ ] **Step 6: 回歸既有 playground service 測試**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python -m pytest src/apps/playground/ -v`
Expected: 全部 PASS（若既有測試檔案名稱不同，用 `find "AI 短片系統 Prismreel/src/apps/playground" -iname "test_*.py"` 先列出實際檔案再逐一確認）

- [ ] **Step 7: Commit**

```bash
git add src/apps/playground/service.py src/apps/playground/test_service_deevid.py
git commit -m "feat(deevid): wire quota check into video generation dispatch

Checks remaining credit_ledger points before calling DeeVidModel;
quota is only spent after a successful generation, so a DeeVid-side
failure (e.g. content policy rejection) never burns points."
```

---

### Task 6: `GET /usage/deevid-credits` API 端點

**Files:**
- Modify: `src/apps/comic_gen/api.py`（新增端點，緊鄰既有 `GET /usage/me`）
- Test: `src/apps/comic_gen/test_api_deevid_credits.py`

**Interfaces:**
- Consumes: Task 1 的 `credit_ledger.get_remaining_points(now_ts=None) -> int`, `credit_ledger.current_period(now_ts=None) -> (float, float)`, `credit_ledger.TOTAL_POINTS_PER_PERIOD`
- Produces: `GET /usage/deevid-credits` 回傳 JSON `{"used": int, "remaining": int, "total": int, "period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD"}`，供 Task 7 前端呼叫

- [ ] **Step 1: 找到既有 `/usage/me` 端點的確切程式碼與其身份驗證依賴**

Run: `grep -n -A5 '@app.get("/usage/me")' "AI 短片系統 Prismreel/src/apps/comic_gen/api.py"`

確認回傳前已看過的內容（`api.py:362-365`）：
```python
@app.get("/usage/me")
def get_my_usage(user=Depends(auth.require_login)):
    return {"user_id": user.id, "summary": usage_repo.get_user_usage_summary(user.id)}
```

**既有 API 測試慣例**（見 `src/apps/comic_gen/test_api_usage.py`）：用 `fastapi.testclient.TestClient(app)`，`isolated_db` autouse fixture 隔離資料庫，登入走 `client.post("/auth/login", json={"email": ..., "password": ...})`，使用者建立走 `user_repo.create_user(email, password, role="admin")`（`role` 選填，預設 member）。本任務沿用同一套慣例。

- [ ] **Step 2: 寫失敗測試**

```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo, user_repo, credit_ledger
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    importlib.reload(user_repo)
    importlib.reload(credit_ledger)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def _client():
    from src.apps.comic_gen.api import app
    return TestClient(app)


def test_deevid_credits_requires_login():
    client = _client()
    resp = client.get("/usage/deevid-credits")
    assert resp.status_code == 401


def test_deevid_credits_returns_full_quota_when_unused():
    from src.apps.comic_gen import user_repo

    user_repo.create_user("creditsuser@example.com", "pw123456")
    client = _client()
    client.post("/auth/login", json={"email": "creditsuser@example.com", "password": "pw123456"})

    resp = client.get("/usage/deevid-credits")

    assert resp.status_code == 200
    body = resp.json()
    assert body["used"] == 0
    assert body["remaining"] == 600
    assert body["total"] == 600
    assert "period_start" in body and "period_end" in body


def test_deevid_credits_reflects_recorded_usage():
    from src.apps.comic_gen import user_repo, credit_ledger

    user_repo.create_user("creditsuser2@example.com", "pw123456")
    credit_ledger.record_usage(points=20, duration=5, task_id="task-1")

    client = _client()
    client.post("/auth/login", json={"email": "creditsuser2@example.com", "password": "pw123456"})
    resp = client.get("/usage/deevid-credits")

    assert resp.status_code == 200
    body = resp.json()
    assert body["used"] == 20
    assert body["remaining"] == 580
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python -m pytest src/apps/comic_gen/test_api_deevid_credits.py -v`
Expected: FAIL — `404 Not Found`（端點尚未存在）

- [ ] **Step 4: 在 `api.py` 新增端點**

緊接在既有 `GET /usage/me`（`api.py:362-365`）之後新增：

```python
@app.get("/usage/deevid-credits")
def get_deevid_credits(user=Depends(auth.require_login)):
    from datetime import datetime, timezone
    from . import credit_ledger

    now_ts = time.time()
    start, end = credit_ledger.current_period(now_ts)
    remaining = credit_ledger.get_remaining_points(now_ts)
    used = credit_ledger.TOTAL_POINTS_PER_PERIOD - remaining

    return {
        "used": used,
        "remaining": remaining,
        "total": credit_ledger.TOTAL_POINTS_PER_PERIOD,
        "period_start": datetime.fromtimestamp(start, tz=timezone.utc).strftime("%Y-%m-%d"),
        "period_end": datetime.fromtimestamp(end, tz=timezone.utc).strftime("%Y-%m-%d"),
    }
```

`api.py` 檔案頂部已有 `import time`（第 30 行），不需要新增這個 import。

- [ ] **Step 5: 執行測試確認全部通過**

Run: `cd "AI 短片系統 Prismreel" && .venv/Scripts/python -m pytest src/apps/comic_gen/test_api_deevid_credits.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/apps/comic_gen/api.py src/apps/comic_gen/test_api_deevid_credits.py
git commit -m "feat(deevid): add GET /usage/deevid-credits endpoint

Surfaces remaining quota, current cycle bounds, and used/total points
for the frontend usage page card."
```

---

### Task 7: 前端 — 用量頁 DeeVid 額度卡片

**Files:**
- Modify: `frontend/src/lib/api.ts`（新增 `getDeeVidCredits()`）
- Modify: `frontend/src/app/usage/page.tsx`（新增額度卡片 UI）
- Modify: `frontend/messages/zh-Hant.json`、`frontend/messages/zh.json`、`frontend/messages/en.json`（新增文案 key）

**Interfaces:**
- Consumes: Task 6 的 `GET /usage/deevid-credits` → `{used, remaining, total, period_start, period_end}`
- Produces: `getDeeVidCredits(): Promise<{used: number; remaining: number; total: number; period_start: string; period_end: string}>`（`api.ts` 匯出函式，供 `usage/page.tsx` 呼叫）

**已確認的既有頁面結構**（`frontend/src/app/usage/page.tsx`）：`useTranslations("usage")` namespace；`getMyUsage()` 用 `useState`/`useEffect` 抓資料、`loading` state 顯示 `{t("loading")}`；頁面主體是 `max-w-3xl mx-auto space-y-4` 容器內依序渲染 `<h1>` 標題列 + `costEstimateNote` 說明文字 + 三個 `<UsageTable>`。新卡片會插入在 `costEstimateNote` 之後、`<UsageTable>` 之前。

- [ ] **Step 1: 在 `api.ts` 新增 `getDeeVidCredits`**

緊接在既有 `getMyUsage`/`getAllUsersUsage`（`api.ts:111-121`）之後新增：

```typescript
export type DeeVidCredits = {
    used: number;
    remaining: number;
    total: number;
    period_start: string;
    period_end: string;
};

export async function getDeeVidCredits(): Promise<DeeVidCredits> {
    const res = await axios.get(`${API_URL}/usage/deevid-credits`);
    return res.data;
}
```

- [ ] **Step 2: 在 `usage/page.tsx` 新增額度卡片**

修改 import 區塊：

```typescript
import { getMyUsage, getDeeVidCredits, type UsageSummary, type DeeVidCredits } from "@/lib/api";
```

新增一個卡片元件（放在既有 `UsageTable` function 定義之後、`UsagePage` export 之前）：

```typescript
function DeeVidCreditsCard({ credits }: { credits: DeeVidCredits }) {
    const t = useTranslations("usage");
    const pct = credits.total > 0 ? Math.min(100, (credits.used / credits.total) * 100) : 0;

    return (
        <div className="glass-panel atelier-card p-6 mb-6">
            <h2 className="text-lg font-display mb-3">{t("deevidCreditsTitle")}</h2>
            <div className="w-full h-2 rounded-full bg-surface-inset overflow-hidden mb-2">
                <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
            </div>
            <p className="text-sm text-text-secondary">
                {t("deevidCreditsUsed", { used: credits.used, total: credits.total })}
            </p>
            <p className="text-sm text-text-secondary">
                {t("deevidCreditsRemaining", { remaining: credits.remaining })}
            </p>
            <p className="text-xs text-text-muted mt-1">
                {t("deevidCreditsPeriod", { start: credits.period_start, end: credits.period_end })}
            </p>
        </div>
    );
}
```

在 `UsagePage` 元件內，新增第二個 state 並在同一個 `useEffect` 內並行抓取（不要新增第二個 `useEffect`，兩個請求互相獨立，用 `Promise.allSettled` 讓其中一個失敗不影響另一個）：

```typescript
export default function UsagePage() {
    const t = useTranslations("usage");
    const router = useRouter();
    const [summary, setSummary] = useState<UsageSummary | null>(null);
    const [deevidCredits, setDeevidCredits] = useState<DeeVidCredits | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.allSettled([getMyUsage(), getDeeVidCredits()])
            .then(([usageResult, creditsResult]) => {
                if (usageResult.status === "fulfilled") {
                    setSummary(usageResult.value.summary);
                } else {
                    router.push("/");
                }
                if (creditsResult.status === "fulfilled") {
                    setDeevidCredits(creditsResult.value);
                }
            })
            .finally(() => setLoading(false));
    }, [router]);
```

在 JSX 內，`{t("costEstimateNote")}` 段落之後、第一個 `<UsageTable ...>` 之前插入：

```tsx
                {deevidCredits && <DeeVidCreditsCard credits={deevidCredits} />}
```

- [ ] **Step 3: 新增 i18n key（三語言檔）**

在 `frontend/messages/zh-Hant.json` 找到既有用量頁使用的 namespace（Step 1 讀 `usage/page.tsx` 的 `useTranslations("<namespace>")` 呼叫可知道是哪個 key），新增：

```json
"deevidCreditsTitle": "DeeVid 額度",
"deevidCreditsUsed": "已用 {used} / {total} 點",
"deevidCreditsRemaining": "剩餘 {remaining} 點",
"deevidCreditsPeriod": "本期：{start} ～ {end}"
```

`zh.json` 對應簡體版本，`en.json` 對應：

```json
"deevidCreditsTitle": "DeeVid Credits",
"deevidCreditsUsed": "{used} / {total} points used",
"deevidCreditsRemaining": "{remaining} points remaining",
"deevidCreditsPeriod": "Current cycle: {start} – {end}"
```

- [ ] **Step 4: Typecheck**

Run: `cd "AI 短片系統 Prismreel/frontend" && npx tsc --noEmit`
Expected: 無錯誤輸出

- [ ] **Step 5: 瀏覽器實測（比照既有 CLAUDE.md L2/L3 驗收慣例，UI 改動必做視覺驗收）**

啟動本機開發環境（`npm run dev:backend` + `npm run dev`），登入後前往「我的用量」頁，確認：
1. DeeVid 額度卡片正確顯示 `0 / 600 點` 或當前實際用量
2. 截圖存證

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/app/usage/page.tsx frontend/messages/en.json frontend/messages/zh.json frontend/messages/zh-Hant.json
git commit -m "feat(deevid): show DeeVid credit quota card on the usage page

Displays used/remaining/total points and the current reset cycle,
sourced from GET /usage/deevid-credits."
```

---

### Task 8: 端到端真實驗收

**Files:** 無程式碼改動，本任務為驗收步驟

**Interfaces:** N/A

- [ ] **Step 1: 在 VPS 或本機 `.env` 補上真實 `DEEVID_API_KEY`（僅本機 `.env` 檔案，不進 git）**

- [ ] **Step 2: 透過影片生成頁選擇 DeeVid Quality V4.0，上傳一張圖片，設定 5 秒，送出生成**

Expected: 生成成功，影片可預覽/下載

- [ ] **Step 3: 驗證 `credit_ledger` 確實寫入一筆 20 點記錄**

Run（本機或 VPS）:
```bash
.venv/Scripts/python -c "
import sys; sys.path.insert(0, '.')
from src.apps.comic_gen import auth_db
conn = auth_db.get_connection()
rows = conn.execute('SELECT * FROM credit_ledger ORDER BY created_at DESC LIMIT 1').fetchall()
print(dict(rows[0]) if rows else 'NO ROWS')
"
```
Expected: 最新一筆 `points=20, duration=5`

- [ ] **Step 4: 呼叫 `/usage/deevid-credits`，確認 `remaining` 減少 20**

- [ ] **Step 5: 前往「我的用量」頁截圖，確認額度卡片顯示正確**

- [ ] **Step 6: （選擇性，若使用者同意消耗額外真實額度）手動在 `credit_ledger` insert 假資料頂到接近 600，測試硬擋是否正確觸發，測試完成後刪除這些假資料列**

```bash
.venv/Scripts/python -c "
import sys; sys.path.insert(0, '.')
from src.apps.comic_gen import auth_db, credit_ledger
conn = auth_db.get_connection()
conn.execute(\"DELETE FROM credit_ledger WHERE task_id IS NULL\")  # 清掉測試插入的假資料（task_id為None是Step 6插入時的標記）
conn.commit()
"
```

- [ ] **Step 7: 向使用者回報驗收結果**
