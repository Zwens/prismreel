# Usage Tracking (Token / Generation Count) — Design

Date: 2026-09-11
Status: Approved for planning

## Problem

PrismReel has no usage accounting anywhere in the stack:

- `LLMAdapter._chat_once` (`src/apps/comic_gen/llm_adapter.py:140`) discards
  `response.usage` from the OpenAI-compatible client and returns only the
  message content string. Every LLM call (novel parsing, storyboard
  extraction, prompt polishing, style analysis) throws away its token count.
- Image/video generation providers (`src/models/byteplus.py`, `kling.py`,
  `vidu.py`, `wanx.py`, `image.py`) have no call counter anywhere.
- `auth_db.py`'s `users` table (SQLite, `output/auth.db`) has no usage/quota
  columns. The multi-tenant auth system (in progress, feature branch
  `feature/multi-tenant-auth`) has no concept of per-user consumption.

This blocks visibility into per-user cost/usage, which is needed before any
future quota or billing feature can exist.

## Scope

In scope:
- LLM text call token counts (prompt/completion) per call.
- Image/video generation call counts per provider/model.
- Per-user cumulative totals.
- A user-facing `/usage` page and an admin-facing usage view.

Out of scope (explicitly deferred):
- Converting counts into a cost amount — no official per-unit pricing is
  available yet for the video/image providers. Revisit once a price table
  exists.
- Quota enforcement / cutting off over-limit users. This design only lays
  the groundwork (an events table keyed by user_id); enforcement is a
  separate future task.

## Architecture

### Storage

Add one new table to the existing SQLite DB (`output/auth.db`, managed by
`auth_db.py`) — no new database file:

```sql
CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,              -- 'llm' | 'image' | 'video'
    provider TEXT NOT NULL,          -- 'dashscope' | 'openai' | 'byteplus' | 'kling' | 'vidu' | 'wanx' | ...
    model TEXT,                      -- model name/id, nullable if unknown
    tokens_prompt INTEGER,           -- null for image/video events
    tokens_completion INTEGER,       -- null for image/video events
    count INTEGER NOT NULL DEFAULT 1,-- always 1 per row; summed at query time
    created_at REAL NOT NULL
)
```

One row per call. Aggregation (sums, per-provider breakdowns) happens at
query time via `usage_repo.py`, not at write time — keeps writes trivial and
avoids race conditions on a shared counter.

### Recording point: caller-side, not provider-side

Rejected alternative: have each of `byteplus.py` / `kling.py` / `vidu.py` /
`wanx.py` / `image.py` write to `usage_events` internally. Rejected because
it touches 5 provider files, couples every provider to the DB layer, and
every future new provider has to remember to add it.

Chosen approach: record usage where calls are actually dispatched —
`pipeline.py` / `api.py` — right after a `model.generate(...)` or
`llm.chat(...)` call succeeds. Adding a new provider later needs zero usage
tracking code inside the provider; only the one dispatch call site needs a
one-line addition.

Two touch points to make this possible:

1. `LLMAdapter._chat_once` (and thus `chat()`) must surface
   `response.usage` (prompt_tokens/completion_tokens) to the caller instead
   of swallowing it. `chat()`'s return shape changes from `str` to a small
   result carrying both the content and usage — exact shape (e.g. a
   dataclass vs a tuple) is an implementation-time decision; every existing
   `self.llm.chat(...)` call site in `llm.py` will need its unpacking
   updated accordingly.
2. Image/video `generate()` calls don't have a token concept — the caller
   just records `count=1` per successful call, with `provider`/`model`
   taken from what was already being passed to `generate()`.

### Repository layer

New `src/apps/comic_gen/usage_repo.py`, mirroring the existing repo pattern
in `auth_db.py`:

- `record_llm_usage(user_id, provider, model, tokens_prompt, tokens_completion)`
- `record_generation_usage(user_id, kind, provider, model)`
- `get_user_usage_summary(user_id)` — per-kind/provider totals for one user
- `get_all_users_usage_summary()` — same, grouped by user, for admin view

### API endpoints

- `GET /usage/me` — current user's usage summary (uses existing
  `auth.get_current_user_from_cookie`)
- `GET /admin/usage` — all users' usage summary, gated by existing
  `auth.require_admin` dependency

### Frontend

- New standalone page `frontend/src/app/usage/page.tsx` — the user's own
  LLM token totals + generation counts by provider/model.
- Admin backend gets a new "Usage" tab/section showing `get_all_users_usage_summary()`.
- `SettingsPage.tsx` and `EnvConfigDialog.tsx` each get a single link/entry
  point to `/usage` — no usage data embedded inline in either form (avoids
  adding a third surface to the pair that already has to be kept in sync,
  per `feedback_env_config_settings_duplicate_surfaces_must_sync.md`).

## Data flow

```
User action (parse novel / polish prompt / generate image / generate video)
  → pipeline.py / api.py dispatches to llm.chat() or model.generate()
  → on success: usage_repo.record_llm_usage(...) or record_generation_usage(...)
  → usage_events row inserted (fire-and-forget; failure to record must not
    fail the underlying user-facing operation)
  → GET /usage/me or /admin/usage reads aggregated sums on demand
```

## Error handling

Recording usage must never break the actual generation flow. Wrap the
`usage_repo.record_*` call in try/except at the call site; log on failure,
don't raise. A lost usage row is acceptable; a failed novel-parse because
the usage insert hit a lock is not.

## Testing

- Unit test `usage_repo.py`: insert events, verify summary aggregation math.
- Unit test `LLMAdapter.chat()` returns usage alongside content for a mocked
  OpenAI-compatible response.
- Manual/API-level check: trigger one LLM call and one image/video call
  through the running app, then confirm `GET /usage/me` reflects both.
