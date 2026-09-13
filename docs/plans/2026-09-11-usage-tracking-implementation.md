# Usage Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record LLM token usage and BytePlus Seedance video-generation token usage per user, convert both to an estimated USD cost, and surface per-user + admin-wide totals in the frontend.

**Architecture:** A new SQLite table (`usage_events`, same DB as `auth_db.py`) is written to from inside `ScriptProcessor` (LLM calls, which already needs a new `user_id` param) and from `pipeline.py`'s video-generation call sites (which resolve `user_id` from `Script.owner_id`). `LLMAdapter` gets a new `chat_with_usage()` method alongside the unchanged `chat()`. `byteplus.py` starts extracting `usage` from Ark's task-status response. Two new FastAPI endpoints expose per-user and admin-wide summaries; a new `/usage` frontend page and an admin tab render them.

**Tech Stack:** Python 3.12, FastAPI, sqlite3 (stdlib), pytest; Next.js 14 App Router, TypeScript, axios, next-intl.

**Spec:** `docs/plans/2026-09-11-usage-tracking-design.md`

## Global Constraints

- LLM subscription rate: $64 USD / 10,000,000 tokens. `cost_usd = total_tokens / 10_000_000 * 64`.
- Seedance price table (USD / M tokens, online inference) — exact values from the design spec, keyed by Ark wire model id + resolution bucket:
  - `dreamina-seedance-2-5-260628`: 480p/720p → 10.70 (no video input) / 6.40 (with video input); 1080p → 11.7 / 7.0 (currently time-limited -28%, applied at write time as a flag not baked into the constant — see Task 2).
  - `dreamina-seedance-2-0-260128`: 480p/720p → 7.0 / 4.3; 1080p → 7.7 / 4.7; 4K → 4.0 / 2.4.
  - `dreamina-seedance-2-0-fast-260128`: 480p/720p → 5.6 / 3.3 (time-limited -25%).
  - `dreamina-seedance-2-0-mini-260615`: 480p/720p → 3.5 / 2.1 (time-limited -60%).
- `cost_usd` is computed once at write time and stored — never recomputed at query time.
- `chat()` on `LLMAdapter` keeps its existing signature and string return type. Do not change any of the 9 existing `self.llm.chat(...)` call sites in `llm.py`.
- Recording usage must never raise into the caller's control flow — wrap every `usage_repo` call at the call site in try/except, log on failure.
- `kling.py`, `vidu.py`, `wanx.py`, `image.py` are untouched. Their generation calls are recorded as count-only (`total_tokens=None`, `cost_usd=None`).
- New frontend pages/components must have `en`, `zh-Hant`, and `zh` entries in `frontend/messages/*.json` — no hardcoded UI strings.
- Every new file follows the existing repo pattern in `auth_db.py`/`user_repo.py`: `get_connection()` → try/finally → `conn.close()`.

---

### Task 1: `usage_events` table + `usage_repo.py` core CRUD (no pricing yet)

**Files:**
- Modify: `src/apps/comic_gen/auth_db.py` (add table DDL to `init_schema`)
- Create: `src/apps/comic_gen/usage_repo.py`
- Test: `src/apps/comic_gen/test_usage_repo.py`

**Interfaces:**
- Produces:
  - `usage_repo.record_llm_usage(user_id: str, provider: str, model: str, tokens_prompt: Optional[int], tokens_completion: Optional[int], total_tokens: Optional[int]) -> None`
  - `usage_repo.record_generation_usage(user_id: str, kind: str, provider: str, model: str, resolution: Optional[str] = None, input_has_video: Optional[bool] = None, total_tokens: Optional[int] = None) -> None`
  - `usage_repo.get_user_usage_summary(user_id: str) -> dict`
  - `usage_repo.get_all_users_usage_summary() -> list[dict]`
  - `UsageEvent` dataclass with fields matching the table columns.

This task adds the table and the four public functions with cost always
`None` (pricing logic is Task 2, kept separate so this task's tests don't
depend on the price table being right).

- [ ] **Step 1: Write the failing test for schema creation**

```python
# src/apps/comic_gen/test_usage_repo.py
import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def test_usage_events_table_exists():
    from src.apps.comic_gen import auth_db

    conn = auth_db.get_connection()
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='usage_events'"
        ).fetchone()
        assert row is not None
    finally:
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest src/apps/comic_gen/test_usage_repo.py::test_usage_events_table_exists -v`
Expected: FAIL — table does not exist yet.

- [ ] **Step 3: Add the table DDL to `auth_db.py`**

Add this `conn.execute(...)` call inside `init_schema`, after the existing
`invites` table block (before `conn.commit()`):

```python
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT,
                resolution TEXT,
                input_has_video INTEGER,
                tokens_prompt INTEGER,
                tokens_completion INTEGER,
                total_tokens INTEGER,
                cost_usd REAL,
                count INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL
            )
            """
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest src/apps/comic_gen/test_usage_repo.py::test_usage_events_table_exists -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for record + summary functions**

```python
def test_record_llm_usage_and_summary():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_llm_usage(
        user_id="u1", provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=100, tokens_completion=50, total_tokens=150,
    )
    usage_repo.record_llm_usage(
        user_id="u1", provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=200, tokens_completion=100, total_tokens=300,
    )
    summary = usage_repo.get_user_usage_summary("u1")
    assert summary["llm"]["dashscope"]["qwen3.7-plus"]["total_tokens"] == 450
    assert summary["llm"]["dashscope"]["qwen3.7-plus"]["count"] == 2


def test_record_generation_usage_count_only():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_generation_usage(
        user_id="u1", kind="video", provider="kling", model="kling-v2",
    )
    usage_repo.record_generation_usage(
        user_id="u1", kind="video", provider="kling", model="kling-v2",
    )
    summary = usage_repo.get_user_usage_summary("u1")
    assert summary["video"]["kling"]["kling-v2"]["count"] == 2
    assert summary["video"]["kling"]["kling-v2"]["total_tokens"] is None
    assert summary["video"]["kling"]["kling-v2"]["cost_usd"] is None


def test_empty_user_id_recorded_under_unknown_bucket():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_llm_usage(
        user_id="", provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=10, tokens_completion=5, total_tokens=15,
    )
    all_summary = usage_repo.get_all_users_usage_summary()
    unknown_entry = next(u for u in all_summary if u["user_id"] in ("", "unknown"))
    assert unknown_entry["summary"]["llm"]["dashscope"]["qwen3.7-plus"]["count"] == 1


def test_get_all_users_usage_summary_groups_by_user():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_llm_usage(
        user_id="u1", provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=10, tokens_completion=5, total_tokens=15,
    )
    usage_repo.record_llm_usage(
        user_id="u2", provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=20, tokens_completion=10, total_tokens=30,
    )
    all_summary = usage_repo.get_all_users_usage_summary()
    ids = {u["user_id"] for u in all_summary}
    assert {"u1", "u2"}.issubset(ids)
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `python -m pytest src/apps/comic_gen/test_usage_repo.py -v`
Expected: FAIL — `usage_repo` module doesn't exist yet.

- [ ] **Step 7: Implement `usage_repo.py`**

```python
# src/apps/comic_gen/usage_repo.py
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from .auth_db import get_connection


@dataclass
class UsageEvent:
    id: str
    user_id: str
    kind: str
    provider: str
    model: Optional[str]
    resolution: Optional[str]
    input_has_video: Optional[bool]
    tokens_prompt: Optional[int]
    tokens_completion: Optional[int]
    total_tokens: Optional[int]
    cost_usd: Optional[float]
    count: int
    created_at: float


def _insert(
    user_id: str,
    kind: str,
    provider: str,
    model: Optional[str],
    resolution: Optional[str] = None,
    input_has_video: Optional[bool] = None,
    tokens_prompt: Optional[int] = None,
    tokens_completion: Optional[int] = None,
    total_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO usage_events
                (id, user_id, kind, provider, model, resolution, input_has_video,
                 tokens_prompt, tokens_completion, total_tokens, cost_usd, count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                str(uuid.uuid4()), user_id, kind, provider, model, resolution,
                None if input_has_video is None else int(input_has_video),
                tokens_prompt, tokens_completion, total_tokens, cost_usd,
                time.time(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def record_llm_usage(
    user_id: str,
    provider: str,
    model: str,
    tokens_prompt: Optional[int],
    tokens_completion: Optional[int],
    total_tokens: Optional[int],
) -> None:
    _insert(
        user_id=user_id, kind="llm", provider=provider, model=model,
        tokens_prompt=tokens_prompt, tokens_completion=tokens_completion,
        total_tokens=total_tokens,
    )


def record_generation_usage(
    user_id: str,
    kind: str,
    provider: str,
    model: str,
    resolution: Optional[str] = None,
    input_has_video: Optional[bool] = None,
    total_tokens: Optional[int] = None,
) -> None:
    _insert(
        user_id=user_id, kind=kind, provider=provider, model=model,
        resolution=resolution, input_has_video=input_has_video,
        total_tokens=total_tokens,
    )


def _rows_to_summary(rows) -> dict:
    summary: dict = {}
    for row in rows:
        kind = row["kind"]
        provider = row["provider"]
        model = row["model"] or "unknown"
        summary.setdefault(kind, {}).setdefault(provider, {}).setdefault(
            model, {"count": 0, "total_tokens": None, "cost_usd": None}
        )
        bucket = summary[kind][provider][model]
        bucket["count"] += row["count"]
        if row["total_tokens"] is not None:
            bucket["total_tokens"] = (bucket["total_tokens"] or 0) + row["total_tokens"]
        if row["cost_usd"] is not None:
            bucket["cost_usd"] = (bucket["cost_usd"] or 0.0) + row["cost_usd"]
    return summary


def get_user_usage_summary(user_id: str) -> dict:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM usage_events WHERE user_id = ?", (user_id,)
        ).fetchall()
        return _rows_to_summary(rows)
    finally:
        conn.close()


def get_all_users_usage_summary() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM usage_events").fetchall()
        by_user: dict = {}
        for row in rows:
            uid = row["user_id"] or "unknown"
            by_user.setdefault(uid, []).append(row)
        return [
            {"user_id": uid, "summary": _rows_to_summary(rows)}
            for uid, rows in by_user.items()
        ]
    finally:
        conn.close()
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest src/apps/comic_gen/test_usage_repo.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 9: Commit**

```bash
git add src/apps/comic_gen/auth_db.py src/apps/comic_gen/usage_repo.py src/apps/comic_gen/test_usage_repo.py
git commit -m "feat(usage): add usage_events table and usage_repo CRUD"
```

---

### Task 2: Seedance pricing table + cost calculation in `usage_repo.py`

**Files:**
- Modify: `src/apps/comic_gen/usage_repo.py`
- Test: `src/apps/comic_gen/test_usage_repo.py` (append)

**Interfaces:**
- Consumes: `_insert()`, `record_llm_usage()`, `record_generation_usage()` from Task 1 (same file — augment, don't replace).
- Produces:
  - `usage_repo.LLM_USD_PER_10M_TOKENS: float = 64.0`
  - `usage_repo.SEEDANCE_PRICING: Dict[str, Dict[str, Tuple[float, float]]]` — model id → resolution bucket → `(no_video_price, with_video_price)` in USD per million tokens.
  - `record_llm_usage(...)` now computes and stores `cost_usd`.
  - `record_generation_usage(..., resolution=..., input_has_video=...)` now computes `cost_usd` when `provider == "byteplus"` and `total_tokens` is given.

- [ ] **Step 1: Write failing tests for cost calculation**

```python
def test_record_llm_usage_computes_cost():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_llm_usage(
        user_id="u1", provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=1_000_000, tokens_completion=0, total_tokens=1_000_000,
    )
    summary = usage_repo.get_user_usage_summary("u1")
    cost = summary["llm"]["dashscope"]["qwen3.7-plus"]["cost_usd"]
    assert cost == pytest.approx(6.4, rel=1e-6)  # 1M/10M * 64


def test_record_seedance_usage_computes_cost_no_video_input():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_generation_usage(
        user_id="u1", kind="video", provider="byteplus",
        model="dreamina-seedance-2-0-260128", resolution="720p",
        input_has_video=False, total_tokens=1_000_000,
    )
    summary = usage_repo.get_user_usage_summary("u1")
    cost = summary["video"]["byteplus"]["dreamina-seedance-2-0-260128"]["cost_usd"]
    assert cost == pytest.approx(7.0, rel=1e-6)


def test_record_seedance_usage_computes_cost_with_video_input():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_generation_usage(
        user_id="u1", kind="video", provider="byteplus",
        model="dreamina-seedance-2-0-260128", resolution="4k",
        input_has_video=True, total_tokens=2_000_000,
    )
    summary = usage_repo.get_user_usage_summary("u1")
    cost = summary["video"]["byteplus"]["dreamina-seedance-2-0-260128"]["cost_usd"]
    assert cost == pytest.approx(4.8, rel=1e-6)  # 2 * 2.4


def test_record_seedance_usage_unknown_resolution_no_cost():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_generation_usage(
        user_id="u1", kind="video", provider="byteplus",
        model="dreamina-seedance-2-0-260128", resolution="does-not-exist",
        input_has_video=False, total_tokens=1_000_000,
    )
    summary = usage_repo.get_user_usage_summary("u1")
    assert summary["video"]["byteplus"]["dreamina-seedance-2-0-260128"]["cost_usd"] is None


def test_record_generation_usage_non_byteplus_no_cost():
    from src.apps.comic_gen import usage_repo

    usage_repo.record_generation_usage(
        user_id="u1", kind="video", provider="wanx", model="wanx-t2v",
        total_tokens=1_000_000,
    )
    summary = usage_repo.get_user_usage_summary("u1")
    assert summary["video"]["wanx"]["wanx-t2v"]["cost_usd"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest src/apps/comic_gen/test_usage_repo.py -k "cost" -v`
Expected: FAIL — `cost_usd` currently always `None`; `SEEDANCE_PRICING` doesn't exist.

- [ ] **Step 3: Add pricing constants and cost logic**

Add near the top of `usage_repo.py`, after the imports:

```python
LLM_USD_PER_10M_TOKENS = 64.0

# USD per 1,000,000 tokens, (price_without_video_input, price_with_video_input).
# "Time limited" discounted rows use the discounted price directly — this is
# a live rate table, not a historical record; update it when BytePlus's
# published pricing changes. See docs/plans/2026-09-11-usage-tracking-design.md
# for the source and date this was captured (2026-09-11).
SEEDANCE_PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "dreamina-seedance-2-5-260628": {
        "480p": (10.70, 6.40),
        "720p": (10.70, 6.40),
        "1080p": (11.7, 7.0),
    },
    "dreamina-seedance-2-0-260128": {
        "480p": (7.0, 4.3),
        "720p": (7.0, 4.3),
        "1080p": (7.7, 4.7),
        "4k": (4.0, 2.4),
    },
    "dreamina-seedance-2-0-fast-260128": {
        "480p": (5.6, 3.3),
        "720p": (5.6, 3.3),
    },
    "dreamina-seedance-2-0-mini-260615": {
        "480p": (3.5, 2.1),
        "720p": (3.5, 2.1),
    },
}


def _llm_cost_usd(total_tokens: Optional[int]) -> Optional[float]:
    if total_tokens is None:
        return None
    return total_tokens / 10_000_000 * LLM_USD_PER_10M_TOKENS


def _seedance_cost_usd(
    model: str,
    resolution: Optional[str],
    input_has_video: Optional[bool],
    total_tokens: Optional[int],
) -> Optional[float]:
    if total_tokens is None or resolution is None:
        return None
    model_prices = SEEDANCE_PRICING.get(model)
    if not model_prices:
        return None
    price_pair = model_prices.get(resolution.lower())
    if not price_pair:
        return None
    price_per_million = price_pair[1] if input_has_video else price_pair[0]
    return total_tokens / 1_000_000 * price_per_million
```

Update `record_llm_usage` to pass `cost_usd=_llm_cost_usd(total_tokens)` into
`_insert(...)`.

Update `record_generation_usage` signature and body:

```python
def record_generation_usage(
    user_id: str,
    kind: str,
    provider: str,
    model: str,
    resolution: Optional[str] = None,
    input_has_video: Optional[bool] = None,
    total_tokens: Optional[int] = None,
) -> None:
    cost_usd = None
    if provider == "byteplus":
        cost_usd = _seedance_cost_usd(model, resolution, input_has_video, total_tokens)
    _insert(
        user_id=user_id, kind=kind, provider=provider, model=model,
        resolution=resolution, input_has_video=input_has_video,
        total_tokens=total_tokens, cost_usd=cost_usd,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest src/apps/comic_gen/test_usage_repo.py -v`
Expected: PASS (all tests from Task 1 + Task 2)

- [ ] **Step 5: Commit**

```bash
git add src/apps/comic_gen/usage_repo.py src/apps/comic_gen/test_usage_repo.py
git commit -m "feat(usage): add LLM and Seedance cost calculation"
```

---

### Task 3: `LLMAdapter.chat_with_usage()`

**Files:**
- Modify: `src/apps/comic_gen/llm_adapter.py`
- Test: `src/apps/comic_gen/test_llm_adapter.py` (new file)

**Interfaces:**
- Consumes: nothing new — same `OpenAI` client already used by `chat()`.
- Produces: `LLMAdapter.chat_with_usage(messages, model=None, response_format=None) -> Tuple[str, Optional[dict], str]`. Third element is the actual model id that served the request — not `_get_default_model()`'s static guess, but whichever candidate in the DashScope fallback chain actually succeeded (or the explicit `model` override, or the OpenAI provider's configured model). This matters because a fallback (e.g. `qwen3.7-plus` unavailable → `qwen3.6-plus` used instead) must be recorded under the model that actually ran, not the first candidate. `usage` dict shape when present: `{"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}`. `chat()` itself is unchanged (still returns a bare `str`).

- [ ] **Step 1: Write the failing test**

```python
# src/apps/comic_gen/test_llm_adapter.py
from unittest.mock import MagicMock, patch


def _mock_openai_response(content: str, usage=None):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    resp.usage = usage
    return resp


def test_chat_with_usage_returns_content_and_usage(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from src.apps.comic_gen.llm_adapter import LLMAdapter

    adapter = LLMAdapter()
    usage_obj = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    mock_response = _mock_openai_response("hello", usage=usage_obj)

    with patch.object(adapter, "_get_client") as get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        get_client.return_value = mock_client

        content, usage, model_used = adapter.chat_with_usage(messages=[{"role": "user", "content": "hi"}])

    assert content == "hello"
    assert usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert model_used == "qwen3.7-plus"  # first DashScope fallback candidate, succeeded on first try


def test_chat_with_usage_handles_missing_usage(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from src.apps.comic_gen.llm_adapter import LLMAdapter

    adapter = LLMAdapter()
    mock_response = _mock_openai_response("hello", usage=None)

    with patch.object(adapter, "_get_client") as get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        get_client.return_value = mock_client

        content, usage, model_used = adapter.chat_with_usage(messages=[{"role": "user", "content": "hi"}])

    assert content == "hello"
    assert usage is None
    assert model_used == "qwen3.7-plus"


def test_chat_with_usage_reports_actual_fallback_model(monkeypatch):
    """When the first candidate is unavailable and the chain falls back,
    the returned model_used must be the one that actually succeeded —
    not _get_default_model()'s static first-candidate guess."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from src.apps.comic_gen.llm_adapter import LLMAdapter

    adapter = LLMAdapter()
    usage_obj = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    ok_response = _mock_openai_response("hello", usage=usage_obj)

    call_count = {"n": 0}

    def fake_create(**kwargs):
        call_count["n"] += 1
        if kwargs["model"] == "qwen3.7-plus":
            raise Exception("Model not found: qwen3.7-plus")
        return ok_response

    with patch.object(adapter, "_get_client") as get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = fake_create
        get_client.return_value = mock_client

        content, usage, model_used = adapter.chat_with_usage(messages=[{"role": "user", "content": "hi"}])

    assert model_used == "qwen3.6-plus"
    assert call_count["n"] == 2


def test_chat_unchanged_string_return(monkeypatch):
    """chat() must still return a bare string — existing 9 call sites in
    llm.py rely on this (some via `.strip()` chaining)."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from src.apps.comic_gen.llm_adapter import LLMAdapter

    adapter = LLMAdapter()
    mock_response = _mock_openai_response("  hello  ")

    with patch.object(adapter, "_get_client") as get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        get_client.return_value = mock_client

        result = adapter.chat(messages=[{"role": "user", "content": "hi"}])

    assert isinstance(result, str)
    assert result.strip() == "hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest src/apps/comic_gen/test_llm_adapter.py -v`
Expected: FAIL — `chat_with_usage` doesn't exist.

- [ ] **Step 3: Implement `chat_with_usage`**

In `llm_adapter.py`, refactor `_chat_once` to return both content and a raw
usage object, and add public methods on top:

```python
    def _chat_once(
        self,
        client,
        model: str,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, str]],
    ):
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content, getattr(response, "usage", None)
        except Exception as e:
            provider_label = "DashScope" if self.provider != "openai" else "OpenAI"
            raise RuntimeError(f"{provider_label} API error: {e}") from e
```

`chat()` now unpacks and discards usage to keep its return type unchanged:

```python
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> str:
        content, _usage = self._chat_with_usage_impl(messages, model, response_format)
        return content

    def chat_with_usage(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, Optional[Dict[str, int]], str]:
        return self._chat_with_usage_impl(messages, model, response_format)
```

Rename the existing fallback-chain body (currently inline in `chat()`) into
a shared `_chat_with_usage_impl` that both public methods call — it's the
same fallback-chain logic as before, just also threading the usage object
and the actual model id that succeeded through to the caller:

```python
    def _chat_with_usage_impl(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str],
        response_format: Optional[Dict[str, str]],
    ) -> Tuple[str, Optional[Dict[str, int]], str]:
        client = self._get_client()

        if model:
            content, usage = self._chat_once(client, model, messages, response_format)
            return content, self._normalize_usage(usage), model

        if self.provider == "openai":
            openai_model = self._get_default_model()
            content, usage = self._chat_once(client, openai_model, messages, response_format)
            return content, self._normalize_usage(usage), openai_model

        last_err: Optional[Exception] = None
        for idx, candidate in enumerate(self._DASHSCOPE_MODEL_FALLBACK_CHAIN):
            try:
                content, usage = self._chat_once(client, candidate, messages, response_format)
                return content, self._normalize_usage(usage), candidate
            except RuntimeError as e:
                msg = str(e).lower()
                is_model_unavailable = any(k in msg for k in (
                    "model not found", "invalidmodel", "model_not_found",
                    "no such model", "not supported", "modelnotfound", "404",
                ))
                last_err = e
                if is_model_unavailable and idx < len(self._DASHSCOPE_MODEL_FALLBACK_CHAIN) - 1:
                    next_candidate = self._DASHSCOPE_MODEL_FALLBACK_CHAIN[idx + 1]
                    logger.warning(
                        "DashScope model %s unavailable (%s); falling back to %s",
                        candidate, e, next_candidate,
                    )
                    continue
                raise
        raise last_err if last_err else RuntimeError("DashScope: no models available")

    @staticmethod
    def _normalize_usage(usage) -> Optional[Dict[str, int]]:
        if usage is None:
            return None
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
        }
```

Add `Tuple` to the `typing` import at the top of the file if not already
present (it is not — current imports are `Dict, List, Optional, Any`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest src/apps/comic_gen/test_llm_adapter.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Run the full existing test suite to confirm no regression**

Run: `python -m pytest src/apps/comic_gen/ -v -k "not integration"`
Expected: PASS — no existing test touching `LLMAdapter.chat()` should break
since its signature and return type are unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/apps/comic_gen/llm_adapter.py src/apps/comic_gen/test_llm_adapter.py
git commit -m "feat(usage): add LLMAdapter.chat_with_usage without changing chat()"
```

---

### Task 4: `ScriptProcessor` records LLM usage (user_id param on all 9 methods)

**Files:**
- Modify: `src/apps/comic_gen/llm.py`
- Test: `src/apps/comic_gen/test_llm.py` (new file, or append if one exists — check first with `ls src/apps/comic_gen/test_llm*.py`)

**Interfaces:**
- Consumes: `usage_repo.record_llm_usage(...)` (Task 1/2), `LLMAdapter.chat_with_usage(...)` (Task 3).
- Produces: All 9 `ScriptProcessor` public methods gain `user_id: Optional[str] = None` as their last parameter (keyword-compatible, default preserves every existing caller unchanged): `parse_novel`, `split_into_episodes`, `analyze_script_for_styles`, `analyze_to_storyboard`, `refine_frame_to_rich`, `polish_storyboard_prompt`, `polish_video_prompt`, `polish_r2v_prompt`. (`create_draft_script` does not call the LLM — no change needed.)

This task only changes the LLM-calling methods to use `chat_with_usage`
and record afterward; it does not yet change any caller (that's Task 6).
Every method keeps its existing return value and behavior — `user_id` is
additive.

- [ ] **Step 1: Write the failing test for one representative method**

```python
# src/apps/comic_gen/test_llm.py
from unittest.mock import patch


def test_parse_novel_records_usage_when_user_id_given(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()

    from src.apps.comic_gen.llm import ScriptProcessor

    processor = ScriptProcessor()
    fake_json = '{"characters": [], "scenes": [], "props": []}'

    with patch.object(
        processor.llm, "chat_with_usage",
        return_value=(fake_json, {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}, "qwen3.7-plus"),
    ):
        processor.parse_novel("Title", "Some novel text", user_id="user-123")

    summary = usage_repo.get_user_usage_summary("user-123")
    assert summary["llm"]["dashscope"]["qwen3.7-plus"]["total_tokens"] == 150


def test_parse_novel_no_user_id_records_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()

    from src.apps.comic_gen.llm import ScriptProcessor

    processor = ScriptProcessor()
    fake_json = '{"characters": [], "scenes": [], "props": []}'

    with patch.object(
        processor.llm, "chat_with_usage",
        return_value=(fake_json, {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}),
    ):
        processor.parse_novel("Title", "Some novel text")  # no user_id — existing callers do this

    all_summary = usage_repo.get_all_users_usage_summary()
    assert all_summary == [] or all(u["user_id"] == "" for u in all_summary)
```

Note: `qwen3.7-plus` here assumes the DashScope fallback chain's first
candidate is used — `chat_with_usage`'s mock bypasses the real chain, so
the recorded `model` must come from whatever `parse_novel` passes as the
`model` argument to `record_llm_usage`. See Step 3 for exactly what to pass.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest src/apps/comic_gen/test_llm.py -v`
Expected: FAIL — `parse_novel` doesn't accept `user_id` yet, and `chat_with_usage` isn't called.

- [ ] **Step 3: Modify `parse_novel` (and the other 8 methods) to accept `user_id` and record usage**

In `llm.py`, add the import at the top:

```python
from . import usage_repo
```

For `parse_novel` (around line 399), change the signature and body:

```python
    def parse_novel(self, title: str, text: str, custom_extraction_prompt: str = "", user_id: Optional[str] = None) -> Script:
        logger.info(f"Parsing novel: {title}...")

        if not self.is_configured:
             logger.error("LLM API key not configured.")
             raise ValueError("LLM API Key 未配置。请在 API 配置中设置对应的 API Key 后重试。")

        prompt = self._construct_prompt(text, custom_extraction_prompt)

        try:
            content, usage, model_used = self.llm.chat_with_usage(
                messages=[{"role": "user", "content": prompt}],
            )
            self._record_llm_usage_safe(user_id, usage, model_used)
            logger.debug(f"LLM Response Content:\n{content}")

            content = _strip_markdown_json(content)
            data = json.loads(content)
            return self._create_script_from_data(title, text, data)

        except json.JSONDecodeError as e:
            error_msg = f"LLM 返回的数据格式错误，无法解析 JSON: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
        except ValueError:
            raise
        except Exception as e:
            error_msg = f"剧本解析失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
```

Add this shared helper as a `ScriptProcessor` method (used by all 9
methods, so define it once, near `_construct_prompt`):

```python
    def _record_llm_usage_safe(self, user_id: Optional[str], usage: Optional[Dict[str, int]], model_used: str) -> None:
        if not usage:
            return
        try:
            usage_repo.record_llm_usage(
                user_id=user_id or "",
                provider=self.llm.provider,
                model=model_used,
                tokens_prompt=usage.get("prompt_tokens"),
                tokens_completion=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            )
        except Exception:
            logger.warning("Failed to record LLM usage", exc_info=True)
```

Repeat the same pattern for the other 8 methods — each one:
1. adds `user_id: Optional[str] = None` as its last parameter,
2. changes its `self.llm.chat(...)` call(s) to `self.llm.chat_with_usage(...)`,
3. unpacks `content, usage, model_used = ...` where it used to do `content = ...`,
4. calls `self._record_llm_usage_safe(user_id, usage, model_used)` right after the call succeeds,
5. keeps every other line unchanged.

The exact call sites (confirmed via `grep -n "self.llm.chat(" src/apps/comic_gen/llm.py` — line numbers below are from that grep, pre-edit):

- `split_into_episodes`, line 620: `content = self.llm.chat(...)`, no `.strip()` chained — becomes `content, usage, model_used = self.llm.chat_with_usage(...)`.
- `analyze_script_for_styles`, line 772: same shape, no `.strip()` chained.
- `analyze_to_storyboard`, **two call sites**, both with `.strip()` chained on the closing paren (`).strip()`):
  - line 945 (`content = self.llm.chat(...).strip()`) — becomes:
    ```python
    content, usage, model_used = self.llm.chat_with_usage(
        messages=[...],  # unchanged args
    )
    content = content.strip()
    self._record_llm_usage_safe(user_id, usage, model_used)
    ```
  - line 959 (`retry_content = self.llm.chat(...).strip()`) — same transform, variable name stays `retry_content`; record usage here too (this is the retry path, still a real call that consumed tokens).
- `refine_frame_to_rich`, line 1109: has `.strip()` chained — same transform as line 945.
- `polish_storyboard_prompt`, line 1164: has `.strip()` chained — same transform.
- `polish_video_prompt`, line 1286: has `.strip()` chained AND an explicit `model=polish_model or None` argument already passed to `chat()`. When `model` is explicitly passed, `chat_with_usage`'s `model_used` return value equals that same explicit model string (per Task 3's `_chat_with_usage_impl`, the `if model:` branch returns the passed-in `model` verbatim) — so `model_used` here will be `polish_model` when the caller supplied one, not a DashScope fallback candidate. Pass `model=polish_model or None` through to `chat_with_usage` unchanged; the transform is otherwise identical to line 945's.
- `polish_r2v_prompt`, line 1430: identical shape to line 1286 (also passes `model=polish_model or None`).

For `polish_video_prompt` and `polish_r2v_prompt` specifically: these raise
`PolishError` on failure (`api_error`, `json_parse_error`, etc.) — only
record usage on the success path, i.e. after the `self.llm.chat_with_usage(...)`
call inside the `try` block returns successfully, not inside the
`except Exception as e: raise PolishError(...)` block (a failed call may
still report token usage for the failed attempt in some providers, but this
design does not attempt to capture that — recording only
confirmed-successful calls keeps the accounting simple and matches what the
design spec's Error handling section describes).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest src/apps/comic_gen/test_llm.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Run the full existing test suite for this file's callers**

Run: `python -m pytest src/apps/comic_gen/test_pipeline.py -v`
Expected: PASS — `pipeline.py` calls these methods without `user_id`
(Task 6 adds that); the default `None` must keep all existing behavior
identical.

- [ ] **Step 6: Commit**

```bash
git add src/apps/comic_gen/llm.py src/apps/comic_gen/test_llm.py
git commit -m "feat(usage): ScriptProcessor records LLM usage when given a user_id"
```

---

### Task 5: `byteplus.py` extracts `usage` from Ark task response

**Files:**
- Modify: `src/models/byteplus.py`
- Test: `src/models/test_byteplus.py` (new file, or append — check first with `ls src/models/test_byteplus*.py`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `BytePlusVideoModel.generate(...)` return type changes from
  `Tuple[str, float]` to `Tuple[str, float, Optional[dict]]` — the third
  element is the `usage` dict (`{"completion_tokens": int, "total_tokens": int}`)
  extracted from the Ark task's `succeeded` response, or `None` if absent.
  `_poll()`'s return type changes from `str` (video_url) to
  `Tuple[str, Optional[dict]]`.

This is the one `VideoGenModel` subclass whose public interface changes.
`kling.py`/`vidu.py`/`wanx.py` keep the base class's 2-tuple — do not touch them.

- [ ] **Step 1: Write the failing test**

```python
# src/models/test_byteplus.py
from unittest.mock import patch, MagicMock


def test_poll_extracts_usage_from_succeeded_response(monkeypatch, tmp_path):
    monkeypatch.setenv("ARK_API_KEY", "test-key")
    from src.models.byteplus import BytePlusVideoModel

    model = BytePlusVideoModel({})

    succeeded_response = MagicMock()
    succeeded_response.raise_for_status.return_value = None
    succeeded_response.json.return_value = {
        "status": "succeeded",
        "content": {"video_url": "https://example.com/video.mp4"},
        "usage": {"completion_tokens": 108900, "total_tokens": 108900},
    }

    with patch("src.models.byteplus.requests.get", return_value=succeeded_response):
        video_url, usage = model._poll("task-123")

    assert video_url == "https://example.com/video.mp4"
    assert usage == {"completion_tokens": 108900, "total_tokens": 108900}


def test_poll_handles_missing_usage(monkeypatch):
    monkeypatch.setenv("ARK_API_KEY", "test-key")
    from src.models.byteplus import BytePlusVideoModel

    model = BytePlusVideoModel({})

    succeeded_response = MagicMock()
    succeeded_response.raise_for_status.return_value = None
    succeeded_response.json.return_value = {
        "status": "succeeded",
        "content": {"video_url": "https://example.com/video.mp4"},
    }

    with patch("src.models.byteplus.requests.get", return_value=succeeded_response):
        video_url, usage = model._poll("task-123")

    assert video_url == "https://example.com/video.mp4"
    assert usage is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest src/models/test_byteplus.py -v`
Expected: FAIL — `_poll` currently returns a bare string, not a tuple.

- [ ] **Step 3: Modify `_poll` and `generate`**

In `byteplus.py`, change `_poll`:

```python
    def _poll(self, task_id: str) -> Tuple[str, Optional[dict]]:
        url = f"{self._tasks_url()}/{task_id}"
        deadline = time.time() + MAX_WAIT
        while time.time() < deadline:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json() or {}
            status = data.get("status")
            if status == "succeeded":
                video_url = ((data.get("content") or {}).get("video_url"))
                if not video_url:
                    raise RuntimeError(f"Ark task succeeded without a video url: {data}")
                return video_url, data.get("usage")
            if status == "failed":
                raise RuntimeError(f"Ark generation failed: {data.get('error')}")
            time.sleep(POLL_INTERVAL)
        raise TimeoutError(f"Ark task {task_id} did not finish within {MAX_WAIT}s")
```

Change `generate`'s call site and return statement:

```python
        video_url, usage = self._poll(task_id)
        self._download(video_url, output_path)

        elapsed = time.time() - start
        logger.info("[BytePlus/Seedance] done in %.1fs -> %s", elapsed, output_path)
        return output_path, elapsed, usage
```

Update the method signature's return type annotation:
`def generate(self, ...) -> Tuple[str, float, Optional[dict]]:`

Add `Optional` to the `typing` import at the top of the file if not already
present — check with `grep -n "^from typing" src/models/byteplus.py` first.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest src/models/test_byteplus.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add src/models/byteplus.py src/models/test_byteplus.py
git commit -m "feat(usage): byteplus.py extracts usage.total_tokens from Ark task response"
```

---

### Task 6: Wire `user_id` through `pipeline.py` call sites (LLM + video generation)

**Files:**
- Modify: `src/apps/comic_gen/pipeline.py`
- Test: `src/apps/comic_gen/test_pipeline.py` (append)

**Interfaces:**
- Consumes: `ScriptProcessor`'s `user_id` param (Task 4), `BytePlusVideoModel.generate()`'s 3-tuple return (Task 5), `usage_repo.record_generation_usage` (Task 1/2).
- Produces: `pipeline.py:import_file_and_split` gains `owner_id: str = ""` parameter. No other public `pipeline.py` method signature changes — the rest resolve `user_id` internally from data already in scope.

- [ ] **Step 1: Write the failing test for `create_project` forwarding owner_id**

```python
# append to src/apps/comic_gen/test_pipeline.py
from unittest.mock import patch


def test_create_project_forwards_owner_id_to_script_processor():
    from src.apps.comic_gen.pipeline import ComicGenPipeline

    pipeline = ComicGenPipeline()
    with patch.object(pipeline.script_processor, "create_draft_script") as mock_draft:
        mock_draft.return_value = pipeline.script_processor.create_draft_script("T", "text")
        pipeline.create_project("Title", "text", skip_analysis=True, owner_id="user-abc")

    script = list(pipeline.scripts.values())[-1]
    assert script.owner_id == "user-abc"


def test_video_generation_records_usage_for_byteplus(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()

    from src.apps.comic_gen.pipeline import ComicGenPipeline
    from src.apps.comic_gen.models import VideoTask

    pipeline = ComicGenPipeline()
    script = pipeline.create_project("Title", "text", skip_analysis=True, owner_id="user-xyz")
    task = VideoTask(id="task-1", prompt="a cat", model="seedance-2.0-t2v", resolution="720p")
    script.video_tasks.append(task)

    with patch.object(pipeline, "_byteplus_video_model", None), \
         patch("src.models.byteplus.BytePlusVideoModel.generate") as mock_generate:
        mock_generate.return_value = ("output/video/task-1.mp4", 12.5, {"completion_tokens": 500000, "total_tokens": 500000})
        pipeline.process_video_task(script.id, "task-1")

    summary = usage_repo.get_user_usage_summary("user-xyz")
    assert summary["video"]["byteplus"]["dreamina-seedance-2-0-260128"]["total_tokens"] == 500000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest src/apps/comic_gen/test_pipeline.py -k "owner_id or byteplus" -v`
Expected: FAIL — `create_project` doesn't forward `owner_id` to
`parse_novel`/`create_draft_script` yet (only sets it on the returned
`Script` after the fact); `process_video_task` doesn't record usage.

- [ ] **Step 3: Forward `owner_id` in `create_project`**

In `pipeline.py`, change `create_project` (around line 427-440):

```python
    def create_project(self, title: str, text: str, skip_analysis: bool = False, workflow_mode: str = "i2v_legacy", series_id: Optional[str] = None, owner_id: str = "") -> Script:
        if skip_analysis:
            script = self.script_processor.create_draft_script(title, text)
        else:
            script = self.script_processor.parse_novel(title, text, user_id=owner_id or None)

        script.workflow_mode = workflow_mode
        script.owner_id = owner_id
```

(`create_draft_script` doesn't call the LLM, so it needs no `user_id` — the
`if/else` branches diverge here on purpose.)

- [ ] **Step 4: Forward `owner_id`-derived `user_id` in the other 3 `ScriptProcessor`-calling `pipeline.py` methods**

For `analyze_text_to_frames`, `refine_frame`, `refine_frame_prompt` (each
receives `script_id`), resolve the owner before calling into
`script_processor`:

```python
    def analyze_text_to_frames(self, script_id: str, text: str) -> Script:
        script = self.scripts.get(script_id)
        owner_id = script.owner_id if script else ""
        # ... existing code up to the call site ...
        raw_frames = self.script_processor.analyze_to_storyboard(
            text, entities_json, custom_extraction_prompt,  # existing args, unchanged
            user_id=owner_id or None,
        )
```

Apply the same `owner_id = self.scripts[script_id].owner_id if script_id in self.scripts else ""`
pattern (adjusted to each method's existing local variable names — read the
surrounding code before editing to match the existing style) to
`refine_frame` and `refine_frame_prompt`, passing `user_id=owner_id or None`
into their respective `self.script_processor.refine_frame_to_rich(...)` /
`self.script_processor.polish_storyboard_prompt(...)` calls.

- [ ] **Step 5: Add `owner_id` parameter to `import_file_and_split`**

```python
    def import_file_and_split(self, text: str, suggested_episodes: int = 3, owner_id: str = "") -> List[Dict]:
        return self.script_processor.split_into_episodes(text, suggested_episodes, user_id=owner_id or None)
```

- [ ] **Step 6: Record video generation usage in `process_video_task`**

Right after the `if use_byteplus:` branch's `generate()` call (around line
3351), capture the third return value and record it once the whole
try-block reaches its success point. Change the byteplus call site:

```python
            if use_byteplus:
                if self._byteplus_video_model is None:
                    from ...models.byteplus import BytePlusVideoModel
                    self._byteplus_video_model = BytePlusVideoModel({})
                video_path, _, gen_usage = self._byteplus_video_model.generate(
                    prompt=task.prompt,
                    output_path=output_path,
                    img_url=img_url,
                    img_path=img_path,
                    duration=task.duration,
                    resolution=task.resolution,
                    aspect_ratio=task.ratio or "16:9",
                    seed=task.seed,
                    watermark=bool(task.watermark) if task.watermark is not None else False,
                    generation_mode=task.generation_mode,
                    ref_image_urls=task.reference_image_urls if task.generation_mode == "r2v" else None,
                    model_name=task.model,
                )
                self._record_generation_usage_safe(
                    script.owner_id, "byteplus", task.model, task.resolution,
                    input_has_video=bool(task.reference_image_urls) if task.generation_mode == "r2v" else False,
                    total_tokens=(gen_usage or {}).get("total_tokens"),
                )
```

For the other three branches (`use_vendor_kling`, `use_vendor_vidu`, the
`else` / wanx branch), add a count-only record right after each `generate()`
call, keeping their existing `video_path, _ = ...generate(...)` unpacking
unchanged (their `generate()` still returns a 2-tuple — only
`BytePlusVideoModel` changed):

```python
                self._record_generation_usage_safe(script.owner_id, "kling", task.model, task.resolution)
```

(same call shape for the vidu and wanx branches, substituting the provider
name — `"vidu"`, `"wanx"`).

Add this helper method to `ComicGenPipeline` (near `process_video_task`):

```python
    def _record_generation_usage_safe(
        self, owner_id: str, provider: str, model: Optional[str],
        resolution: Optional[str] = None, input_has_video: Optional[bool] = None,
        total_tokens: Optional[int] = None,
    ) -> None:
        try:
            from . import usage_repo
            usage_repo.record_generation_usage(
                user_id=owner_id or "", kind="video", provider=provider,
                model=model or "unknown", resolution=resolution,
                input_has_video=input_has_video, total_tokens=total_tokens,
            )
        except Exception:
            logger.warning("Failed to record generation usage", exc_info=True)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest src/apps/comic_gen/test_pipeline.py -v`
Expected: PASS (all tests, including the 2 new ones)

- [ ] **Step 8: Commit**

```bash
git add src/apps/comic_gen/pipeline.py src/apps/comic_gen/test_pipeline.py
git commit -m "feat(usage): wire user_id through pipeline.py LLM and video generation call sites"
```

---

### Task 7: Add auth to `/video/polish_prompt` and `/video/polish_r2v_prompt`, wire `user_id`

**Files:**
- Modify: `src/apps/comic_gen/api.py`
- Test: `src/apps/comic_gen/test_api_usage.py` (new file)

**Interfaces:**
- Consumes: `auth.require_login` (existing, used by every other authenticated route), `ScriptProcessor.polish_video_prompt(..., user_id=...)` / `polish_r2v_prompt(..., user_id=...)` (Task 4).
- Produces: Both routes now require a valid login cookie (breaking change for any anonymous caller — see Step 1 note).

- [ ] **Step 1: Confirm current behavior before changing it**

Run: `grep -n "polish_video_prompt\|polish_r2v_prompt" frontend/src/lib/api.ts`

This confirms whether the frontend already sends the auth cookie on these
calls (it does, globally, per `axios.defaults.withCredentials = true` in
`api.ts:50`) — the frontend needs no changes, only the backend route
declarations need the new dependency. If any external non-browser client
calls these two endpoints without a cookie, this change will start
returning 401 for them — acceptable per the user-confirmed decision to add
auth here (see design spec's Recording point section, item 3).

- [ ] **Step 2: Write the failing test**

```python
# src/apps/comic_gen/test_api_usage.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    import importlib
    from src.apps.comic_gen import auth_db, usage_repo, user_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(usage_repo)
    importlib.reload(user_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def _client():
    from src.apps.comic_gen.api import app
    return TestClient(app)


def test_polish_video_prompt_requires_login():
    client = _client()
    resp = client.post("/video/polish_prompt", json={"draft_prompt": "a cat walking"})
    assert resp.status_code == 401


def test_polish_video_prompt_works_when_logged_in(monkeypatch):
    from src.apps.comic_gen import user_repo
    from unittest.mock import patch

    user_repo.create_user("polish@example.com", "pw123456")
    client = _client()
    client.post("/auth/login", json={"email": "polish@example.com", "password": "pw123456"})

    with patch(
        "src.apps.comic_gen.llm.ScriptProcessor.polish_video_prompt",
        return_value={"prompt_cn": "一只猫在走路", "prompt_en": "a cat walking"},
    ):
        resp = client.post("/video/polish_prompt", json={"draft_prompt": "a cat walking"})

    assert resp.status_code == 200
    assert resp.json()["prompt_en"] == "a cat walking"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest src/apps/comic_gen/test_api_usage.py -v`
Expected: FAIL — the route currently accepts the request with no auth
(first test gets 200, not 401).

- [ ] **Step 4: Add `Depends(auth.require_login)` to both routes**

In `api.py`, change the `polish_video_prompt` route (around line 4143-4174):

```python
@app.post("/video/polish_prompt")
def polish_video_prompt(request: PolishVideoPromptRequest, user=Depends(auth.require_login)):
    """..."""
    from .llm import PolishError
    try:
        custom_prompt = _get_custom_prompt(request.script_id, "video_polish")
        polish_model = request.polish_model or _get_polish_model_for_project(request.script_id)
        processor = ScriptProcessor()
        result = processor.polish_video_prompt(
            request.draft_prompt,
            request.feedback,
            custom_prompt,
            request.prev_cn,
            image_urls=request.image_urls or None,
            polish_model=polish_model,
            user_id=user.id,
        )
        return {
            "prompt_cn": result.get("prompt_cn", ""),
            "prompt_en": result.get("prompt_en", "")
        }
    except PolishError as e:
        # ... existing except block unchanged ...
```

Apply the identical pattern to `polish_r2v_prompt` (around line 4203-4230):
add `user=Depends(auth.require_login)` to the signature, pass
`user_id=user.id` as the last argument to
`processor.polish_r2v_prompt(...)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest src/apps/comic_gen/test_api_usage.py -v`
Expected: PASS (both tests)

- [ ] **Step 6: Run the full API test suite to check for regressions**

Run: `python -m pytest src/apps/comic_gen/ -v`
Expected: PASS — no other test should call these two routes without a
session cookie already established (all other tests either don't touch
these routes or already log in first, matching every other authenticated
route's existing pattern).

- [ ] **Step 7: Commit**

```bash
git add src/apps/comic_gen/api.py src/apps/comic_gen/test_api_usage.py
git commit -m "feat(usage): require login on /video/polish_prompt and /video/polish_r2v_prompt"
```

---

### Task 8: `GET /usage/me` and `GET /admin/usage` endpoints

**Files:**
- Modify: `src/apps/comic_gen/api.py`
- Test: `src/apps/comic_gen/test_api_usage.py` (append)

**Interfaces:**
- Consumes: `usage_repo.get_user_usage_summary(user_id)`, `usage_repo.get_all_users_usage_summary()` (Task 1).
- Produces:
  - `GET /usage/me` → `200 {"user_id": str, "summary": dict}` (requires login)
  - `GET /admin/usage` → `200 [{"user_id": str, "summary": dict}, ...]` (requires admin)

- [ ] **Step 1: Write the failing test**

```python
# append to src/apps/comic_gen/test_api_usage.py
def test_usage_me_requires_login():
    client = _client()
    resp = client.get("/usage/me")
    assert resp.status_code == 401


def test_usage_me_returns_own_summary():
    from src.apps.comic_gen import user_repo, usage_repo

    user = user_repo.create_user("usageuser@example.com", "pw123456")
    usage_repo.record_llm_usage(
        user_id=user.id, provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=100, tokens_completion=50, total_tokens=150,
    )

    client = _client()
    client.post("/auth/login", json={"email": "usageuser@example.com", "password": "pw123456"})
    resp = client.get("/usage/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == user.id
    assert body["summary"]["llm"]["dashscope"]["qwen3.7-plus"]["total_tokens"] == 150


def test_admin_usage_requires_admin_role():
    from src.apps.comic_gen import user_repo

    user_repo.create_user("regular@example.com", "pw123456")
    client = _client()
    client.post("/auth/login", json={"email": "regular@example.com", "password": "pw123456"})
    resp = client.get("/admin/usage")
    assert resp.status_code == 403


def test_admin_usage_returns_all_users():
    from src.apps.comic_gen import user_repo, usage_repo

    admin = user_repo.create_user("adminuser@example.com", "pw123456", role="admin")
    other = user_repo.create_user("otheruser@example.com", "pw123456")
    usage_repo.record_llm_usage(
        user_id=other.id, provider="dashscope", model="qwen3.7-plus",
        tokens_prompt=10, tokens_completion=5, total_tokens=15,
    )

    client = _client()
    client.post("/auth/login", json={"email": "adminuser@example.com", "password": "pw123456"})
    resp = client.get("/admin/usage")

    assert resp.status_code == 200
    ids = {u["user_id"] for u in resp.json()}
    assert other.id in ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest src/apps/comic_gen/test_api_usage.py -k "usage_me or admin_usage" -v`
Expected: FAIL — 404, routes don't exist yet.

- [ ] **Step 3: Add the two routes**

Add to `api.py`, near the other `/admin/*` routes (after
`admin_deactivate_user`, around line 345):

```python
@app.get("/usage/me")
def get_my_usage(user=Depends(auth.require_login)):
    from . import usage_repo
    return {"user_id": user.id, "summary": usage_repo.get_user_usage_summary(user.id)}


@app.get("/admin/usage")
def admin_get_all_usage(_admin=Depends(auth.require_admin)):
    from . import usage_repo
    return usage_repo.get_all_users_usage_summary()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest src/apps/comic_gen/test_api_usage.py -v`
Expected: PASS (all 6 tests in this file)

- [ ] **Step 5: Commit**

```bash
git add src/apps/comic_gen/api.py src/apps/comic_gen/test_api_usage.py
git commit -m "feat(usage): add GET /usage/me and GET /admin/usage endpoints"
```

---

### Task 9: Frontend API client functions + types

**Files:**
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Produces:
  - `type UsageBucket = { count: number; total_tokens: number | null; cost_usd: number | null }`
  - `type UsageSummary = Record<string, Record<string, Record<string, UsageBucket>>>` (kind → provider → model → bucket)
  - `getMyUsage(): Promise<{ user_id: string; summary: UsageSummary }>`
  - `getAllUsersUsage(): Promise<{ user_id: string; summary: UsageSummary }[]>`

No test file for this task — it's a thin typed wrapper with no logic to
unit test; it's exercised by the pages built in Tasks 10-11 and verified
manually in Task 12.

- [ ] **Step 1: Add the types and functions to `api.ts`**

Add after `adminDeactivateUser` (around line 98):

```typescript
export type UsageBucket = {
    count: number;
    total_tokens: number | null;
    cost_usd: number | null;
};

export type UsageSummary = Record<string, Record<string, Record<string, UsageBucket>>>;

export async function getMyUsage(): Promise<{ user_id: string; summary: UsageSummary }> {
    const res = await axios.get(`${API_URL}/usage/me`);
    return res.data;
}

export async function getAllUsersUsage(): Promise<{ user_id: string; summary: UsageSummary }[]> {
    const res = await axios.get(`${API_URL}/admin/usage`);
    return res.data;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors introduced by this change.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(usage): add frontend API client for usage endpoints"
```

---

### Task 10: i18n messages for the usage feature

**Files:**
- Modify: `frontend/messages/en.json`, `frontend/messages/zh-Hant.json`, `frontend/messages/zh.json`

**Interfaces:**
- Produces: a new top-level `"usage"` namespace in all three message files, and one new key `settings.usageLinkLabel` in the existing `"settings"` namespace (for the Settings-page entry link built in Task 12).

- [ ] **Step 1: Add the `usage` namespace to `en.json`**

Add as a new top-level key (matching the existing alphabetical-ish ordering
isn't required — the existing file doesn't enforce one; add it at the end
before the closing `}`):

```json
  "usage": {
    "pageTitle": "Usage",
    "myUsageTitle": "My Usage",
    "adminUsageTitle": "All Users' Usage",
    "llmSection": "LLM Text Generation",
    "videoSection": "Video Generation",
    "otherSection": "Other Generation (count only)",
    "columnProvider": "Provider",
    "columnModel": "Model",
    "columnCount": "Calls",
    "columnTokens": "Tokens",
    "columnCost": "Est. Cost (USD)",
    "costEstimateNote": "Costs are estimates based on published pricing and may not reflect your exact bill.",
    "noCostAvailable": "—",
    "loading": "Loading...",
    "backToSettings": "Back to Settings"
  }
```

Add this one key inside the existing `"settings"` object (anywhere among
its siblings):

```json
    "usageLinkLabel": "View usage & estimated cost",
```

Also add this key inside the existing `"project"` object (confirmed via
`grep -n 'useTranslations' frontend/src/components/project/EnvConfigDialog.tsx`
— that dialog uses the `"project"` namespace, not `"settings"`):

```json
    "usageLinkLabel": "View usage & estimated cost",
```

- [ ] **Step 2: Add the equivalent keys to `zh-Hant.json`**

```json
  "usage": {
    "pageTitle": "用量",
    "myUsageTitle": "我的用量",
    "adminUsageTitle": "所有使用者用量",
    "llmSection": "LLM 文字生成",
    "videoSection": "影片生成",
    "otherSection": "其他生成（僅計次數）",
    "columnProvider": "供應商",
    "columnModel": "模型",
    "columnCount": "呼叫次數",
    "columnTokens": "Token 數",
    "columnCost": "預估費用（美元）",
    "costEstimateNote": "費用為依官方公開價目表估算，可能與實際帳單有出入。",
    "noCostAvailable": "—",
    "loading": "載入中...",
    "backToSettings": "返回設定"
  }
```

```json
    "usageLinkLabel": "查看用量與預估費用",
```

And inside `"project"`:

```json
    "usageLinkLabel": "查看用量與預估費用",
```

- [ ] **Step 3: Add the equivalent keys to `zh.json`**

```json
  "usage": {
    "pageTitle": "用量",
    "myUsageTitle": "我的用量",
    "adminUsageTitle": "所有用户用量",
    "llmSection": "LLM 文本生成",
    "videoSection": "视频生成",
    "otherSection": "其他生成（仅计次数）",
    "columnProvider": "供应商",
    "columnModel": "模型",
    "columnCount": "调用次数",
    "columnTokens": "Token 数",
    "columnCost": "预估费用（美元）",
    "costEstimateNote": "费用为依官方公开价目表估算，可能与实际账单有出入。",
    "noCostAvailable": "—",
    "loading": "加载中...",
    "backToSettings": "返回设置"
  }
```

```json
    "usageLinkLabel": "查看用量与预估费用",
```

And inside `"project"`:

```json
    "usageLinkLabel": "查看用量与预估费用",
```

- [ ] **Step 4: Verify all three JSON files are valid**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('messages/en.json'))" && node -e "JSON.parse(require('fs').readFileSync('messages/zh-Hant.json'))" && node -e "JSON.parse(require('fs').readFileSync('messages/zh.json'))"`
Expected: no output (no parse errors).

- [ ] **Step 5: Commit**

```bash
git add frontend/messages/en.json frontend/messages/zh-Hant.json frontend/messages/zh.json
git commit -m "feat(usage): add i18n messages for usage feature"
```

---

### Task 11: `/usage` page (personal view)

**Files:**
- Create: `frontend/src/app/usage/page.tsx`

**Interfaces:**
- Consumes: `getMyUsage()` (Task 9), `"usage"` i18n namespace (Task 10).

- [ ] **Step 1: Write the page**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { getMyUsage, type UsageSummary } from "@/lib/api";

function UsageTable({ summary, kind, title, showCost }: { summary: UsageSummary; kind: string; title: string; showCost: boolean }) {
    const t = useTranslations("usage");
    const providers = summary[kind] || {};
    const rows: { provider: string; model: string; count: number; total_tokens: number | null; cost_usd: number | null }[] = [];
    for (const [provider, models] of Object.entries(providers)) {
        for (const [model, bucket] of Object.entries(models)) {
            rows.push({ provider, model, ...bucket });
        }
    }
    if (rows.length === 0) return null;

    return (
        <div className="glass-panel atelier-card p-6 mb-6">
            <h2 className="text-lg font-display mb-3">{title}</h2>
            <table className="w-full text-sm">
                <thead>
                    <tr className="text-left border-b border-glass-border">
                        <th className="pb-2">{t("columnProvider")}</th>
                        <th className="pb-2">{t("columnModel")}</th>
                        <th className="pb-2">{t("columnCount")}</th>
                        <th className="pb-2">{t("columnTokens")}</th>
                        {showCost && <th className="pb-2">{t("columnCost")}</th>}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r) => (
                        <tr key={`${r.provider}-${r.model}`} className="border-b border-glass-border last:border-0">
                            <td className="py-2">{r.provider}</td>
                            <td className="py-2">{r.model}</td>
                            <td className="py-2">{r.count}</td>
                            <td className="py-2">{r.total_tokens ?? t("noCostAvailable")}</td>
                            {showCost && (
                                <td className="py-2">
                                    {r.cost_usd != null ? `$${r.cost_usd.toFixed(4)}` : t("noCostAvailable")}
                                </td>
                            )}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default function UsagePage() {
    const t = useTranslations("usage");
    const router = useRouter();
    const [summary, setSummary] = useState<UsageSummary | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        getMyUsage()
            .then((data) => setSummary(data.summary))
            .finally(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <p className="text-text-secondary">{t("loading")}</p>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background p-8">
            <div className="max-w-3xl mx-auto space-y-4">
                <div className="flex items-center justify-between">
                    <h1 className="text-2xl font-display">{t("myUsageTitle")}</h1>
                    <button onClick={() => router.push("/")} className="text-primary hover:underline text-sm">
                        {t("backToSettings")}
                    </button>
                </div>
                <p className="text-xs text-text-muted">{t("costEstimateNote")}</p>
                {summary && (
                    <>
                        <UsageTable summary={summary} kind="llm" title={t("llmSection")} showCost={true} />
                        <UsageTable summary={summary} kind="video" title={t("videoSection")} showCost={true} />
                        <UsageTable summary={summary} kind="image" title={t("otherSection")} showCost={false} />
                    </>
                )}
            </div>
        </div>
    );
}
```

- [ ] **Step 2: Manually verify the page loads**

Run the app (`npm run dev` in `frontend/`, backend already running per
project's existing dev workflow), log in as a test user, navigate to
`/usage`. Expected: page renders without a console error, shows
`myUsageTitle` heading and (if the user has no recorded usage yet) no
tables — this is correct per `UsageTable`'s early-return when `rows.length === 0`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/usage/page.tsx
git commit -m "feat(usage): add personal /usage page"
```

---

### Task 12: Admin usage tab + Settings/EnvConfigDialog entry links

**Files:**
- Modify: `frontend/src/app/admin/dashboard/page.tsx`
- Modify: `frontend/src/components/settings/SettingsPage.tsx`
- Modify: `frontend/src/components/project/EnvConfigDialog.tsx`

**Interfaces:**
- Consumes: `getAllUsersUsage()` (Task 9), `"usage"` and `"settings"` i18n namespaces (Task 10).

- [ ] **Step 1: Add a usage section to the admin dashboard**

In `frontend/src/app/admin/dashboard/page.tsx`, add the import:

```typescript
import { getAllUsersUsage, type UsageSummary } from "@/lib/api";
import { useTranslations } from "next-intl";
```

Add state and a fetch call inside the component:

```typescript
    const t = useTranslations("usage");
    const [usageData, setUsageData] = useState<{ user_id: string; summary: UsageSummary }[]>([]);
```

In the existing `useEffect`, after `setAuthorized(true);`, add a parallel
fetch (don't block the existing `adminListUsers()` chain — fire and forget
into its own state):

```typescript
                setAuthorized(true);
                getAllUsersUsage().then(setUsageData).catch(() => {});
                return adminListUsers();
```

Add a new section to the JSX, after the existing users table's closing
`</div>` (before the outermost `</div></div>`):

```tsx
                <div className="glass-panel atelier-card p-6">
                    <h2 className="text-lg font-display mb-3">{t("adminUsageTitle")}</h2>
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left border-b border-glass-border">
                                <th className="pb-2">User ID</th>
                                <th className="pb-2">{t("columnCost")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {usageData.map((u) => {
                                let totalCost = 0;
                                for (const providers of Object.values(u.summary)) {
                                    for (const models of Object.values(providers)) {
                                        for (const bucket of Object.values(models)) {
                                            if (bucket.cost_usd != null) totalCost += bucket.cost_usd;
                                        }
                                    }
                                }
                                return (
                                    <tr key={u.user_id} className="border-b border-glass-border last:border-0">
                                        <td className="py-2 font-mono text-xs">{u.user_id || "unknown"}</td>
                                        <td className="py-2">${totalCost.toFixed(4)}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
```

- [ ] **Step 2: Add an entry link in `SettingsPage.tsx`'s About section**

Locate the "Technical info table" block (around line 940-950, identified
during planning) and add a link right after the `aboutRows.map(...)` block,
before the FFmpeg row:

```tsx
        <div className="pt-2">
            <a href="/usage" className="text-primary hover:underline text-sm">
                {t("usageLinkLabel")}
            </a>
        </div>
```

(`t` here is already `useTranslations("settings")`, already in scope at
the top of the component — this reads the `settings.usageLinkLabel` key
added in Task 10.)

- [ ] **Step 3: Add the same link in `EnvConfigDialog.tsx`**

File: `frontend/src/components/project/EnvConfigDialog.tsx` (confirmed
path — this project's own documented gotcha notes these two forms
(`SettingsPage.tsx`/`EnvConfigDialog.tsx`) must be kept in sync:
`memory/feedback_env_config_settings_duplicate_surfaces_must_sync.md`).
This dialog uses the `"project"` i18n namespace (confirmed via
`useTranslations("project")` at line 98 — **not** `"settings"`), so Task 10
already added a `project.usageLinkLabel` key for it.

Add the link to the footer button row (around line 514-534, the
`<div className="flex justify-end gap-3 p-6 border-t border-glass-border">`
block that currently holds only the Cancel and Save buttons). Add it as a
new element before that div's closing buttons, using `justify-between`
instead of `justify-end` so the link sits on the left and the existing
buttons stay right-aligned:

```tsx
          <div className="flex justify-between items-center gap-3 p-6 border-t border-glass-border">
            <a href="/usage" className="text-primary hover:underline text-sm">
              {t("usageLinkLabel")}
            </a>
            <div className="flex gap-3">
              <button
                onClick={requestClose}
                disabled={!canClose}
                className="px-4 py-2 text-sm text-text-secondary hover:text-foreground transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {tc("cancel")}
              </button>
              <button
                onClick={handleSave}
                disabled={saving || loading || !!loadError}
                className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-foreground text-sm font-medium rounded-lg transition-all disabled:opacity-50"
              >
                {saving ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    {t("savingConfig")}
                  </>
                ) : (
                  <>
                    <Save size={16} />
                    {t("saveConfig")}
                  </>
                )}
              </button>
            </div>
          </div>
```

(`t` here is already `useTranslations("project")`, in scope at line 98 —
this reads the `project.usageLinkLabel` key added in Task 10.)

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/admin/dashboard/page.tsx frontend/src/components/settings/SettingsPage.tsx frontend/src/components/project/EnvConfigDialog.tsx
git commit -m "feat(usage): add admin usage tab and settings entry links"
```

---

### Task 13: End-to-end manual verification

**Files:** none (verification only)

- [ ] **Step 1: Start the backend and frontend**

Follow this project's existing dev-start procedure (check
`memory/MEMORY.md` or `package.json` scripts if unfamiliar — do not guess
the command).

- [ ] **Step 2: Trigger one LLM call through the UI**

Log in, open a project, use the video-prompt polish feature (the UI path
that hits `/video/polish_prompt`).

- [ ] **Step 3: Trigger one Seedance video generation through the UI**

Generate a video using a Seedance model.

- [ ] **Step 4: Check `GET /usage/me` reflects both**

Navigate to `/usage` in the browser. Expected: LLM section shows one row
with `dashscope`/the model used, non-zero tokens, and a computed cost;
Video section shows one row for `byteplus`/the Seedance model id used,
non-zero tokens, and a computed cost matching the price table.

- [ ] **Step 5: Confirm attribution is correct, not "unknown"**

Check the `usage_events` table directly:

```bash
python -c "
import sqlite3
conn = sqlite3.connect('output/auth.db')
conn.row_factory = sqlite3.Row
for row in conn.execute('SELECT user_id, kind, provider, model, total_tokens, cost_usd FROM usage_events ORDER BY created_at DESC LIMIT 5'):
    print(dict(row))
"
```

Expected: `user_id` matches the logged-in test user's id (from `GET
/auth/me`), not an empty string.

- [ ] **Step 6: Check the admin view**

Log in as an admin user, navigate to `/admin`, confirm the new usage
section shows the test user's total estimated cost.

- [ ] **Step 7: Run the full backend test suite one more time**

Run: `python -m pytest src/ -v`
Expected: PASS, no regressions across the whole change.

- [ ] **Step 8: Report completion**

No commit for this task (verification only) — if any step surfaces a bug,
fix it as a new commit referencing which task's code it corrects, then
re-run this task's steps from the beginning.
