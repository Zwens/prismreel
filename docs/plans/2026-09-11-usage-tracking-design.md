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
- LLM text call token counts (prompt/completion) per call, converted to a
  cost estimate against the user's subscription rate ($64 / 10M tokens).
- BytePlus Seedance (video) generation token counts per call — the Ark API
  returns real `usage.total_tokens` per completed task — converted to a
  cost estimate using BytePlus's official per-model, per-resolution price
  table (see "Pricing reference" below).
- Other image/video providers (`kling.py`, `vidu.py`, `wanx.py`, `image.py`):
  call counts only, no cost conversion — no confirmed per-unit price or
  token-bearing response format for these yet.
- Per-user cumulative totals.
- A user-facing `/usage` page and an admin-facing usage view.

Out of scope (explicitly deferred):
- Cost conversion for kling/vidu/wanx/image.py — revisit once their pricing
  and response formats are confirmed the same way Seedance's was.
- Quota enforcement / cutting off over-limit users. This design only lays
  the groundwork (an events table keyed by user_id); enforcement is a
  separate future task.

### Pricing reference (confirmed 2026-09-11)

**LLM subscription**: $64 USD / 10,000,000 tokens (user's DashScope/OpenAI
plan). Cost = `total_tokens / 10_000_000 * 64`.

**BytePlus Seedance (Ark video generation)**: billed in USD per million
tokens, varying by model id, output resolution, and whether the input
includes a video. Ark's "retrieve task" response includes a real
`usage.total_tokens` field (input tokens are always 0 for video models —
confirmed BytePlus behavior, only output is billed). Price table (USD / M
tokens, online inference; see BytePlus ModelArk pricing docs, effective
2026-09-11 — some rows carry a time-limited discount, re-check before
relying on this table long-term):

| Model id (as used in `ARK_MODEL_IDS`) | Resolution | No video input | With video input |
|---|---|---|---|
| `dreamina-seedance-2-5-260628` | 480p/720p | 10.70 | 6.40 |
| `dreamina-seedance-2-5-260628` | 1080p (time-limited -28%) | 11.7 list | 7.0 list |
| `dreamina-seedance-2-0-260128` | 480p/720p | 7.0 | 4.3 |
| `dreamina-seedance-2-0-260128` | 1080p | 7.7 | 4.7 |
| `dreamina-seedance-2-0-260128` | 4K | 4.0 | 2.4 |
| `dreamina-seedance-2-0-fast-260128` | 480p/720p (time-limited -25%) | 5.6 list | 3.3 list |
| `dreamina-seedance-2-0-mini-260615` | 480p/720p (time-limited -60%) | 3.5 list | 2.1 list |

This table must live in code as data (not hardcoded inline in the cost
formula) so it can be updated without touching call sites — see
`usage_repo.py` design below.

## Architecture

### Storage

Add one new table to the existing SQLite DB (`output/auth.db`, managed by
`auth_db.py`) — no new database file:

```sql
CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,           -- may be '' for pre-migration/legacy records; not FK-enforced for that reason
    kind TEXT NOT NULL,              -- 'llm' | 'video' | 'image'
    provider TEXT NOT NULL,          -- 'dashscope' | 'openai' | 'byteplus' | 'kling' | 'vidu' | 'wanx' | ...
    model TEXT,                      -- model name/id, nullable if unknown
    resolution TEXT,                 -- e.g. '720p', '1080p', '4k'; null when not applicable (LLM rows, other providers)
    input_has_video INTEGER,         -- 0/1/null; only meaningful for Seedance-style video rows
    tokens_prompt INTEGER,           -- null for count-only events
    tokens_completion INTEGER,       -- null for count-only events
    total_tokens INTEGER,            -- null for count-only events; authoritative token count from the provider response
    cost_usd REAL,                   -- computed at write time from the price table; null when no price is known
    count INTEGER NOT NULL DEFAULT 1,-- always 1 per row; summed at query time
    created_at REAL NOT NULL
)
```

One row per call. `cost_usd` is computed once at write time (using the price
table snapshot in `usage_repo.py` at the time of the call) and stored
directly — not recomputed at query time — so historical rows keep their
original cost even if the price table (or a time-limited discount) changes
later. Aggregation (sums, per-provider breakdowns) still happens at query
time via `usage_repo.py`; only the per-row cost is fixed at write time.

### Recording point (revised after plan-review — see below for why the naive design doesn't work)

Rejected alternative 1: have each of `byteplus.py` / `kling.py` / `vidu.py` /
`wanx.py` / `image.py` write to `usage_events` internally. Rejected because
it touches 5 provider files, couples every provider to the DB layer, and
every future new provider has to remember to add it.

Rejected alternative 2 (the original version of this spec): "record usage
in `pipeline.py`/`api.py` right after `llm.chat()`/`model.generate()`
succeeds." This turned out to be wrong once traced through the actual call
graph during plan-review:

- The code that knows `user_id` (`api.py` route handlers, via
  `Depends(get_owned_script)` / `Depends(auth.require_login)`) does **not**
  directly call `llm.chat()`. It calls business-level `ScriptProcessor`
  methods (`llm.py`, 9 public methods: `parse_novel`, `split_into_episodes`,
  `analyze_script_for_styles`, `analyze_to_storyboard`,
  `refine_frame_to_rich`, `polish_storyboard_prompt`, `polish_video_prompt`,
  `polish_r2v_prompt`). `ScriptProcessor` is the thing that actually calls
  `llm.chat()`, and it has no `user_id` anywhere in its method signatures.
- Storing usage on an adapter/processor instance attribute (e.g.
  `self.llm.last_usage`) is unsafe: `pipeline = ComicGenPipeline()` in
  `api.py:230` is a module-level singleton, so `pipeline.script_processor`
  (and its `LLMAdapter`) is shared across all concurrent requests. Two
  users' calls racing would let one overwrite the other's usage before it's
  read. Usage must flow through an explicit return value, never shared
  mutable state.

**Actual chosen design:**

1. `LLMAdapter` gets a new method `chat_with_usage(...)` returning
   `(content, usage_dict_or_None)`, sharing the same `_chat_once` internals.
   The existing `chat()` method's signature and string return type are
   **unchanged** — all 9 existing `self.llm.chat(...)` call sites in
   `llm.py` (several used as `self.llm.chat(...).strip()`) need zero edits.
   `usage_dict` is `None` when the provider response has no `usage` field
   (must be handled defensively — not guaranteed present on every
   OpenAI-compatible-but-not-OpenAI backend).
2. `ScriptProcessor`'s 9 public methods each get a new
   `user_id: Optional[str] = None` parameter (default preserves existing
   callers). Internally, methods that need usage recording switch their
   `self.llm.chat(...)` call to `self.llm.chat_with_usage(...)` and, on
   success, call `usage_repo.record_llm_usage(user_id, ...)` themselves
   (wrapped in try/except — see Error handling). This makes
   `ScriptProcessor` the recording point for LLM calls, not `pipeline.py`/
   `api.py` — it's the only layer that both calls the LLM and can be handed
   a `user_id`.
3. Callers of `ScriptProcessor` methods supply `user_id` from what they
   already have on hand — no new lookups required in most cases:
   - `pipeline.py:create_project` already receives `owner_id` as a
     parameter (existing code, just not yet forwarded to
     `script_processor.parse_novel`) — forward it.
   - `pipeline.py:analyze_text_to_frames` / `refine_frame` /
     `refine_frame_prompt` receive `script_id` — resolve
     `self.scripts[script_id].owner_id` (the `Script` model already has
     this field — `models.py:551`, populated since the multi-tenant auth
     work landed; empty string for pre-migration records).
   - `pipeline.py:import_file_and_split` has neither `script_id` nor
     `owner_id` in its signature (it runs before a `Script` exists) — add
     an `owner_id: str = ""` parameter, forwarded from its `api.py` callers
     (`/series/import/preview`, `/series/import/confirm`, both already have
     `Depends(auth.require_login)`).
   - `api.py`'s two direct `ScriptProcessor()` call sites
     (`/video/polish_prompt`, `/video/polish_r2v_prompt`) currently have
     **no auth dependency at all** — confirmed by reading the route
     definitions (`api.py:4144`, `api.py:4204`); both take a plain Pydantic
     body with no `Request`/`Depends`. Add `user=Depends(auth.require_login)`
     to both (matching the pattern every other authenticated route in this
     file already uses) and pass `user.id` through.
4. Video generation (`pipeline.py`, 4 call sites inside
   `process_video_task` and friends, all of which have `script_id` in
   scope) resolves `user_id` the same way as #3's `script_id`-based cases:
   `self.scripts[script_id].owner_id`. After a successful
   `model.generate(...)` call, if the provider is BytePlus/Seedance, also
   read `usage.total_tokens` from the Ark task response (see below) and
   call `usage_repo.record_generation_usage(..., total_tokens=...)`; for
   kling/vidu/wanx, call it with `total_tokens=None` (count-only).
5. `byteplus.py::_poll()` currently discards everything in the Ark task
   response except `status` and `content.video_url` (`byteplus.py:234-240`).
   It must also extract `data.get("usage")` (confirmed shape:
   `{"completion_tokens": ..., "total_tokens": ...}`, prompt tokens always 0
   for video) and return it alongside the video path — `generate()`'s
   return type changes from `Tuple[str, float]` to a 3-tuple (or a small
   result object) adding the usage dict. This is the one `VideoGenModel`
   subclass whose public interface actually changes; `kling.py`/`vidu.py`/
   `wanx.py` are untouched and keep returning the base class's
   `Tuple[str, float]` — their call sites just pass `total_tokens=None`.

### Repository layer

New `src/apps/comic_gen/usage_repo.py`, mirroring the existing repo pattern
in `auth_db.py`. Holds the price table (as a Python constant, e.g.
`SEEDANCE_PRICING: Dict[str, Dict[str, Tuple[float, float]]]` keyed by
model id → resolution → (no_video_price, with_video_price) per million
tokens) and the LLM subscription rate (`LLM_USD_PER_10M_TOKENS = 64`) so
both live in one place, not scattered across call sites.

- `record_llm_usage(user_id, provider, model, tokens_prompt, tokens_completion, total_tokens)`
  — computes `cost_usd = total_tokens / 10_000_000 * 64` and stores it.
- `record_generation_usage(user_id, kind, provider, model, resolution=None, input_has_video=None, total_tokens=None)`
  — when `provider == "byteplus"` and `total_tokens` is given, looks up
  `SEEDANCE_PRICING[model][resolution]` and computes `cost_usd`; otherwise
  stores `cost_usd=None` (count-only, e.g. kling/vidu/wanx).
- `get_user_usage_summary(user_id)` — per-kind/provider totals (count,
  summed tokens, summed cost_usd) for one user.
- `get_all_users_usage_summary()` — same, grouped by user, for admin view.

`user_id` may be `""` (empty string) for calls whose caller couldn't
resolve one yet (e.g. a pre-migration `Script.owner_id`) — these rows are
still recorded (grouped under an "unknown" bucket in the summary queries)
rather than silently dropped, since losing the row entirely would make the
totals undercount.

### API endpoints

- `GET /usage/me` — current user's usage summary (uses existing
  `auth.get_current_user_from_cookie`)
- `GET /admin/usage` — all users' usage summary, gated by existing
  `auth.require_admin` dependency

### Frontend

- New standalone page `frontend/src/app/usage/page.tsx` — the user's own
  LLM token totals + estimated cost, Seedance video token totals +
  estimated cost, and other providers' generation counts (no cost) —
  broken down by provider/model.
- Admin backend gets a new "Usage" tab/section showing `get_all_users_usage_summary()`.
- `SettingsPage.tsx` and `EnvConfigDialog.tsx` each get a single link/entry
  point to `/usage` — no usage data embedded inline in either form (avoids
  adding a third surface to the pair that already has to be kept in sync,
  per `feedback_env_config_settings_duplicate_surfaces_must_sync.md`).
- Cost figures are labeled as estimates (e.g. "~$X.XX") since the price
  table can go stale (time-limited discounts expire) and the LLM figure
  depends on the user's specific subscription tier.

## Data flow

```
LLM path:
  api.py route (has user_id via Depends) → ScriptProcessor.xxx(..., user_id=...)
    → self.llm.chat_with_usage(...) → on success: usage_repo.record_llm_usage(...)

Video generation path (pipeline.py):
  process_video_task(script_id, task_id) → resolve user_id from
  self.scripts[script_id].owner_id → model.generate(...)
    → (BytePlus only) usage.total_tokens extracted in byteplus.py::_poll()
    → usage_repo.record_generation_usage(..., total_tokens=... or None)

Both paths: recording is fire-and-forget (try/except, log on failure) —
failure to record must never fail the underlying user-facing operation.

  → GET /usage/me or /admin/usage reads aggregated sums (incl. cost_usd) on demand
```

## Error handling

Recording usage must never break the actual generation flow. Wrap the
`usage_repo.record_*` call in try/except at the call site; log on failure,
don't raise. A lost usage row is acceptable; a failed novel-parse because
the usage insert hit a lock is not.

## Testing

- Unit test `usage_repo.py`: insert events, verify summary aggregation math,
  verify `cost_usd` computation for both the LLM rate and each Seedance
  price table row (including a case with `input_has_video=True` using the
  discounted rate).
- Unit test `LLMAdapter.chat_with_usage()` returns `(content, usage)` for a
  mocked response with a `usage` field, and `(content, None)` for one
  without — confirm `chat()` itself is unchanged (still returns a bare
  string) for a couple of the existing 9 call sites' call shapes.
- Unit test `usage_repo.record_generation_usage` with `total_tokens=None`
  (kling/vidu/wanx path) stores `cost_usd=None`.
- Unit test `byteplus.py::_poll()` extracts `usage` from a mocked Ark
  "succeeded" response and returns it alongside the video path.
- Manual/API-level check: trigger one LLM call (e.g. `/video/polish_prompt`
  after adding auth) and one Seedance video generation through the running
  app, then confirm `GET /usage/me` reflects both with non-null `cost_usd`,
  and that the row is attributed to the correct user (not `""`/unknown).
