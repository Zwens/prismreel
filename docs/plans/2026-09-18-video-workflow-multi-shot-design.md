# Multi-Shot Video Workflow — Design

**Date:** 2026-09-18
**Status:** Approved by user, pending implementation plan

## Problem

`VideoGenPage` (`#/video-gen`) is a single-shot compose tool: one mode, one
prompt, one set of input media, one generate action. There is no way to
build a longer video out of several shots without leaving the app to
concatenate clips by hand.

## Goal

A new, additive workflow where a user assembles a sequence of shots (up to
10), each with its own text prompt and optional image(s)/video, generates
each shot's clip (individually or all at once), then concatenates the
completed clips in order into one finished video — without ever seeing or
choosing technical mode names (t2v/i2v/r2v/v2v).

Out of scope for this iteration: subtitles, BGM, transition effects
between shots, and LLM-driven auto-splitting of one long prompt into shots.

## Non-goals / constraints from brainstorming

- Does not replace or modify `VideoGenPage`, `usePlaygroundStore`, or
  `useGenerationRunner` — those keep serving the single-shot use case.
- Does not reuse `comic_gen`'s `Script`/`Frame`/`RenderEngine` — that model
  carries subtitle/BGM/character concepts this feature does not need yet.
  A future iteration may add subtitles/BGM by adopting that pipeline.
- No LLM call is introduced by this feature.

## User-facing flow

1. User opens the new "Video Workflow" page from the sidebar (alongside,
   not instead of, "Video Studio").
2. User adds shot cards, each with:
   - A prompt text field. Typing `@` opens the existing asset picker;
     a "Pick from library" button opens the same picker.
   - Zero or more images, or one existing video, attached to the shot.
   - Mode is *never* shown or chosen — it's derived from what's attached.
3. User can generate one shot at a time (its own Generate button + status),
   or "Generate all" to run every not-yet-completed shot concurrently.
4. Once every shot is `completed`, "Combine into final video" concatenates
   the shots' output clips in card order and shows/downloads the result.
5. Shot cards can be reordered (drag), inserted at any position via an
   "insert here" affordance between cards, and deleted. Hard cap: 10 shots.

## Mode inference rule

Evaluated per shot from its attached media, in this precedence:

| Attached media | Inferred mode |
|---|---|
| One video | `v2v` |
| ≥2 images (+ optional video ignored per above) | `r2v` |
| Exactly 1 image | `i2v` |
| No media | `t2v` |

A shot with no prompt and no media cannot be generated (Generate button
disabled), mirroring `VideoGenPage`'s `canGenerate` gate.

## Architecture

### Frontend (all new files; nothing existing is modified except the sidebar entry)

- `frontend/src/components/modules/videoworkflow/VideoWorkflowPage.tsx`
  Top-level page: shot list, add/insert/delete/reorder, "Generate all",
  "Combine into final video".
- `frontend/src/components/modules/videoworkflow/ShotCard.tsx`
  One card: prompt input (with `@`-trigger), media attach area (reuses
  `AssetSourcePicker` for library picks, `playgroundApi.uploadMedia`/
  `uploadVideo` for fresh uploads), per-shot status, per-shot Generate.
- `frontend/src/components/modules/videoworkflow/useShotSequenceStore.ts`
  A new, independent zustand store — **not** `usePlaygroundStore** — whose
  shape is a shot array:
  ```ts
  interface Shot {
    id: string;
    prompt: string;
    media: string[];       // image paths, or a single video path
    mediaType: 'image' | 'video' | null;
    mode: PlaygroundMode;  // derived, recomputed on every media/prompt change
    status: 'idle' | 'queued' | 'processing' | 'completed' | 'failed';
    generationId?: string;
    outputPath?: string;
    error?: string;
  }
  ```
  Actions: addShot(atIndex?), removeShot, moveShot, updateShotPrompt,
  updateShotMedia, setShotStatus, reset.
- `frontend/src/components/modules/videoworkflow/useShotGeneration.ts`
  Drives one shot through `playgroundApi.generate` + polls
  `getGenerationStatus`/`getGeneration` to completion, writing status back
  into the store. A thin, shot-scoped sibling of `useGenerationRunner` —
  deliberately not shared, because that hook is wired to the single-compose
  queue/pump model that doesn't fit "N independent shots, each individually
  retriable."
  "Generate all" simply calls this once per not-completed shot; the
  browser's own concurrent-fetch behavior plus each shot's independent
  polling timer gives per-shot parallelism without needing the pump/queue
  machinery `useGenerationRunner` has for the single-compose case.
- Sidebar: add one entry in `GlobalSidebar.tsx` / `page.tsx`'s view union
  (`'videoworkflow'`), following the exact pattern `'videogen'` already
  uses (hash route `#/video-workflow`, `renderContent` branch).

### Backend (all new; nothing existing is modified)

- `src/apps/playground/concat_service.py`
  ```python
  def concat_videos(video_paths: list[str], *, ffmpeg_path: str, output_dir: str) -> str:
      """Concatenate videos in order. Returns the output file's path.

      Tries the concat demuxer first (`-f concat`, stream copy — fast,
      lossless). If probing shows the inputs don't share codec/resolution/
      fps (demuxer concat requires that), or the demuxer run fails, falls
      back to `filter_complex concat` with re-encode. Mirrors the
      demuxer-then-filter_complex fallback comic_gen's merge_videos already
      established for the same reason, but implemented standalone — no
      Script/Frame dependency.
      """
  ```
  Uses `get_ffmpeg_path()` and `probe_dimensions`/`probe_duration` from
  `src/utils/media_probe.py` (already used by `comic_gen/editing.py`) to
  decide which path to take. Output goes to
  `output/playground/videos/` (same dir `service.py` already writes video
  generations to), filename `workflow_{uuid}.mp4`.

- `src/apps/playground/api.py`
  New route:
  ```python
  POST /playground/concat
  body: { "video_paths": ["playground/videos/a.mp4", "playground/videos/b.mp4", ...] }
  -> { "path": "playground/videos/workflow_....mp4" }
  ```
  Auth-gated the same way as every other playground route
  (`Depends(auth.require_login)`). Paths are resolved/validated through
  the existing `resolve_local_media_path` guard before being handed to
  ffmpeg — same guard `upload_media`/`upload_video` already use — so this
  endpoint can't be pointed at an arbitrary filesystem path.

- `frontend/src/lib/api.ts`: add `playgroundApi.concat(videoPaths: string[])`
  following the exact call shape of the other `playgroundApi.*` entries.

## Error handling

- A shot's generation failure sets that shot's `status: 'failed'` +
  `error` message; other shots are unaffected; "Combine" stays disabled
  until every shot is `completed` (failed shots must be retried or
  removed).
- Concat failure (ffmpeg error on both demuxer and filter_complex attempts)
  surfaces as a toast/inline error on the "Combine" button; no partial file
  is left referenced by the UI.

## Testing

- Backend: `tests/test_concat_service.py` — unit tests for
  `concat_videos` covering (a) happy path with matching inputs → demuxer
  path taken, (b) mismatched inputs → filter_complex fallback taken, (c)
  ffmpeg failure surfaces as a raised exception the API layer turns into a
  4xx/5xx. Follows the mocking style of `tests/test_render_engine.py`.
- Frontend: unit tests for the mode-inference function in
  `useShotSequenceStore` (pure function, easy table-driven test) and for
  `addShot`'s insert-at-index behavior.
- Manual/Playwright: build 2-3 shots with mixed media types, generate all,
  combine, verify the final file plays shots in the right order — per this
  workspace's CLAUDE.md L2/L3 verification rules for UI changes.
