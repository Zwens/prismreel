# Multi-Shot Video Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new, additive "Video Workflow" page where a user assembles up to 10 shots (each with a prompt + optional images/video), generates each shot's clip independently or all at once, then concatenates the completed clips in order into one finished video.

**Architecture:** New frontend page + new independent zustand store (shot array) + a thin per-shot generation hook, all reusing existing `playgroundApi` calls and the existing `AssetSourcePicker` component. New backend `concat_service.py` (ffmpeg concat demuxer, re-encode, same approach `comic_gen/pipeline.py:merge_videos` already uses) behind one new `POST /playground/concat` route. Nothing existing (`VideoGenPage`, `usePlaygroundStore`, `useGenerationRunner`, `comic_gen`) is modified except three small additive edits: the sidebar nav list, the hash-router in `page.tsx`, and three i18n message files.

**Tech Stack:** Next.js (React) + zustand frontend; FastAPI + ffmpeg backend; vitest (node env for pure logic, happy-dom for components); pytest backend.

**Spec:** `docs/plans/2026-09-18-video-workflow-multi-shot-design.md`

## Global Constraints

- Max 10 shots per workflow (hard cap, enforced in the store's `addShot`).
- Mode inference precedence (from spec): 1 video → `v2v`; ≥2 images → `r2v`; exactly 1 image → `i2v`; no media → `t2v`. A video attachment takes precedence over any images present.
- No subtitles, no BGM, no transition effects, no LLM-driven auto-split of a long prompt into shots — explicitly out of scope this iteration.
- Nothing in `comic_gen/*`, `usePlaygroundStore.ts`, `useGenerationRunner.ts`, or `VideoGenPage.tsx` is modified.
- Media selection UI reuses `AssetSourcePicker` exactly as `MediaInput.tsx` does today (picker-only; no local drag-and-drop upload in this feature — that gap is tracked separately in `memory/feedback_media_input_upload_removed_beyond_user_intent_2026-09-18.md` and is out of scope here).
- Auth: every new backend route is gated with `Depends(auth.require_login)`, matching every other route in `src/apps/playground/api.py`.
- Path safety: the concat endpoint must resolve every input path through `resolve_local_media_path` before touching the filesystem, rejecting anything that resolves to `None` — matching `apply_grid_to_media`'s existing pattern in `src/apps/playground/api.py:242-255`.
- i18n: new user-facing strings go in `frontend/messages/{en,zh,zh-Hant}.json` under `playground.videoWorkflow.*` (component strings) and `nav.videoworkflow` (sidebar label) — all three files updated together in the same task.
- Node-environment tests (pure logic, no DOM) go in `frontend/src/__tests__/` per `frontend/vitest.config.mts`'s `include` glob — NOT under `src/components/**`, which only `vitest.ui.config.mts` (happy-dom) picks up.

---

## File Structure

**Backend (new):**
- `src/apps/playground/concat_service.py` — `concat_videos()`: ffmpeg concat-demuxer + re-encode, mirrors `comic_gen/pipeline.py:merge_videos`'s proven approach.
- `tests/test_concat_service.py` — unit + real-ffmpeg integration tests.

**Backend (modified, additive only):**
- `src/apps/playground/api.py` — add `POST /playground/concat` route (~15 lines: one function + one `router.add_api_route` call, following the exact shape of `apply_grid_to_media`).

**Frontend (new):**
- `frontend/src/components/modules/videoworkflow/useShotSequenceStore.ts` — shot array store + pure `inferShotMode()` function.
- `frontend/src/components/modules/videoworkflow/useShotGeneration.ts` — drives one shot through `playgroundApi.generate` + polling to completion.
- `frontend/src/components/modules/videoworkflow/ShotCard.tsx` — one shot's UI: prompt input with `@`-trigger, media picker (reuses `AssetSourcePicker`), status, per-shot Generate button.
- `frontend/src/components/modules/videoworkflow/VideoWorkflowPage.tsx` — page shell: shot list, add/insert/delete/reorder, "Generate all", "Combine into final video".
- `frontend/src/__tests__/shot-sequence-store.test.ts` — pure-logic tests for `inferShotMode()` and the store's `addShot`/`removeShot`/`moveShot`.

**Frontend (modified, additive only):**
- `frontend/src/lib/api.ts` — add `playgroundApi.concat()`.
- `frontend/src/components/layout/GlobalSidebar.tsx` — add `"videoworkflow"` to `GlobalTab` union and one entry to `GLOBAL_NAV_ITEMS`.
- `frontend/src/app/page.tsx` — add `'videoworkflow'` to the `currentView` union, one `#/video-workflow` branch in the hash-router effect, and one `renderContent()` branch.
- `frontend/messages/en.json`, `frontend/messages/zh.json`, `frontend/messages/zh-Hant.json` — add `nav.videoworkflow` + `playground.videoWorkflow.*` keys.

---

### Task 1: Backend concat service

**Files:**
- Create: `src/apps/playground/concat_service.py`
- Test: `tests/test_concat_service.py`

**Interfaces:**
- Consumes: `src.utils.system_check.get_ffmpeg_path() -> str` (already exists).
- Produces: `concat_videos(video_paths: list[str], *, ffmpeg_path: str, output_dir: str) -> str` — raises `ConcatError` (defined in this module) on any failure; returns the absolute output file path on success. `VIDEO_OUTPUT_DIR` constant (`os.path.join("output", "playground", "videos")`) — Task 2 imports both.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_concat_service.py
import os
import subprocess

import pytest

from src.apps.playground.concat_service import ConcatError, concat_videos
from src.utils.system_check import get_ffmpeg_path

requires_ffmpeg = pytest.mark.skipif(not get_ffmpeg_path(), reason="ffmpeg not installed")


def _make_test_clip(path: str, color: str = "red", duration: float = 1.0, size: str = "320x240"):
    """Generate a tiny synthetic clip with ffmpeg's testsrc/color source — no
    fixture binary files checked into the repo, and every test controls its
    own inputs' resolution/duration explicitly."""
    ffmpeg = get_ffmpeg_path()
    subprocess.run(
        [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", f"color=c={color}:s={size}:d={duration}:r=24",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            path,
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


def test_concat_videos_missing_input_raises(tmp_path):
    with pytest.raises(ConcatError):
        concat_videos(
            [str(tmp_path / "does_not_exist.mp4")],
            ffmpeg_path=get_ffmpeg_path() or "ffmpeg",
            output_dir=str(tmp_path),
        )


def test_concat_videos_empty_list_raises(tmp_path):
    with pytest.raises(ConcatError):
        concat_videos([], ffmpeg_path=get_ffmpeg_path() or "ffmpeg", output_dir=str(tmp_path))


@requires_ffmpeg
def test_concat_videos_same_resolution(tmp_path):
    clip_a = str(tmp_path / "a.mp4")
    clip_b = str(tmp_path / "b.mp4")
    _make_test_clip(clip_a, color="red", duration=1.0)
    _make_test_clip(clip_b, color="blue", duration=1.0)

    output_dir = str(tmp_path / "out")
    result_path = concat_videos(
        [clip_a, clip_b],
        ffmpeg_path=get_ffmpeg_path(),
        output_dir=output_dir,
    )

    assert os.path.exists(result_path)
    assert result_path.startswith(output_dir)

    from src.utils.media_probe import probe_duration
    total = probe_duration(result_path)
    assert 1.7 < total < 2.3  # ~2s combined, allowing encode rounding


@requires_ffmpeg
def test_concat_videos_mismatched_resolution_still_succeeds(tmp_path):
    """Different-resolution/codec inputs are the normal case here (clips come
    from different AI video models) — re-encode must handle it, unlike a
    stream-copy concat which would hard-fail."""
    clip_a = str(tmp_path / "a.mp4")
    clip_b = str(tmp_path / "b.mp4")
    _make_test_clip(clip_a, color="green", duration=1.0, size="640x480")
    _make_test_clip(clip_b, color="yellow", duration=1.0, size="320x240")

    output_dir = str(tmp_path / "out")
    result_path = concat_videos(
        [clip_a, clip_b],
        ffmpeg_path=get_ffmpeg_path(),
        output_dir=output_dir,
    )
    assert os.path.exists(result_path)


@requires_ffmpeg
def test_concat_videos_ffmpeg_failure_raises_concat_error(tmp_path, monkeypatch):
    clip_a = str(tmp_path / "a.mp4")
    _make_test_clip(clip_a, color="red", duration=1.0)

    with pytest.raises(ConcatError):
        concat_videos(
            [clip_a],
            ffmpeg_path="/nonexistent/ffmpeg/binary",
            output_dir=str(tmp_path / "out"),
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_concat_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.apps.playground.concat_service'`

- [ ] **Step 3: Write the implementation**

```python
# src/apps/playground/concat_service.py
"""Concatenate N video clips, in order, into one file.

Shots in the video-workflow feature come from different AI video models,
so inputs routinely differ in resolution/codec/fps. A stream-copy concat
(`-c copy`) requires identical parameters across every input and fails hard
otherwise, so this always re-encodes — the same trade-off
comic_gen/pipeline.py:merge_videos already made for the same reason. No
subtitles, no audio mixing, no transitions: this is the "just stitch them
in order" step the spec calls for; a richer pipeline (comic_gen's
RenderEngine) is a deliberately separate future step, not reused here.
"""

import os
import subprocess
import uuid

from ...utils import get_logger

logger = get_logger(__name__)

_TIMEOUT_S = 600


class ConcatError(Exception):
    """concat_videos could not produce an output file."""


def concat_videos(video_paths: list, *, ffmpeg_path: str, output_dir: str) -> str:
    """Concatenate `video_paths` in order into one re-encoded mp4.

    Returns the absolute path of the written file. Raises ConcatError if
    the input list is empty, any input is missing, or ffmpeg fails.
    """
    if not video_paths:
        raise ConcatError("No video paths given to concat")

    missing = [p for p in video_paths if not os.path.exists(p)]
    if missing:
        raise ConcatError(f"Input video(s) not found: {missing}")

    os.makedirs(output_dir, exist_ok=True)
    list_path = os.path.join(output_dir, f"concat_list_{uuid.uuid4()}.txt")
    output_filename = f"workflow_{uuid.uuid4()}.mp4"
    output_path = os.path.join(output_dir, output_filename)

    with open(list_path, "w", encoding="utf-8") as f:
        for path in video_paths:
            escaped = path.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    cmd = [
        ffmpeg_path, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]

    logger.info(f"[CONCAT] Merging {len(video_paths)} clip(s) -> {output_filename}")

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=_TIMEOUT_S)
    except FileNotFoundError as e:
        raise ConcatError(f"ffmpeg binary not found at {ffmpeg_path!r}") from e
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace")[-600:] if e.stderr else "(no stderr)"
        raise ConcatError(f"ffmpeg failed: {stderr}") from e
    except subprocess.TimeoutExpired as e:
        raise ConcatError(f"ffmpeg timed out after {_TIMEOUT_S}s") from e
    finally:
        try:
            os.remove(list_path)
        except OSError:
            pass

    if not os.path.exists(output_path):
        raise ConcatError(f"ffmpeg reported success but {output_path} does not exist")

    logger.info(f"[CONCAT] Wrote {output_path}")
    return output_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_concat_service.py -v`
Expected: PASS (5 tests; the two `@requires_ffmpeg` tests skip if ffmpeg is not on PATH, otherwise pass)

- [ ] **Step 5: Commit**

```bash
git add src/apps/playground/concat_service.py tests/test_concat_service.py
git commit -m "feat(playground): add ffmpeg concat service for multi-shot video workflow"
```

---

### Task 2: Backend `/playground/concat` API route

**Files:**
- Modify: `src/apps/playground/api.py` (add imports + one route function + one `router.add_api_route` call, placed after the existing `/upload`, `/upload-video`, `/apply-grid` block at line 260)

**Interfaces:**
- Consumes: `concat_videos`, `ConcatError` from Task 1 (`src.apps.playground.concat_service`); `resolve_local_media_path` from `src.utils.media_refs` (already imported in this file at line 29); `to_posix_media_path` (already imported); `auth.require_login` (already imported).
- Produces: `POST /playground/concat` — body `{"video_paths": ["playground/videos/a.mp4", ...]}` → `{"path": "playground/videos/workflow_xxx.mp4"}` on success, `HTTPException(400)` if any path is invalid/missing, `HTTPException(500)` if ffmpeg fails. This is what Task 6's `playgroundApi.concat()` calls.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_playground_concat_api.py
import io
import os

import pytest
from fastapi.testclient import TestClient

from src.main import app  # adjust import if the FastAPI app lives elsewhere — verify with `grep -rn "app = FastAPI" src/`


@pytest.fixture
def client():
    return TestClient(app)


def _auth_headers(client):
    """Mirrors whatever other playground API tests do to satisfy
    auth.require_login — check tests/test_storage_orphan_recovery.py or an
    existing playground api test for the actual login/token fixture used in
    this repo before writing this fixture for real."""
    raise NotImplementedError("wire this to the existing test auth fixture")


def test_concat_endpoint_rejects_path_outside_output(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/playground/concat",
        json={"video_paths": ["../../etc/passwd"]},
        headers=headers,
    )
    assert resp.status_code == 400


def test_concat_endpoint_rejects_missing_file(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/playground/concat",
        json={"video_paths": ["playground/videos/does_not_exist_12345.mp4"]},
        headers=headers,
    )
    assert resp.status_code == 400
```

**Before running this test**, find the repo's actual FastAPI test-auth pattern: `grep -rn "TestClient\|require_login" src/apps/playground/*.py tests/*.py`. Every existing playground endpoint test already solved "how do I call an authenticated route in a test" — copy that fixture verbatim into `_auth_headers` instead of inventing a new one. If no such test exists yet for this router, check `src/apps/comic_gen/auth.py`'s `require_login` implementation to see whether it's a real session check or a dev-mode bypass, and write the fixture to match.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_playground_concat_api.py -v`
Expected: FAIL (404, since the route doesn't exist yet — or a collection error until `_auth_headers` is wired per the note above)

- [ ] **Step 3: Write the implementation**

Add to `src/apps/playground/api.py`, right after the existing `router.add_api_route("/apply-grid", ...)` line (currently line 260):

```python
from .concat_service import ConcatError, concat_videos
from ...utils.system_check import get_ffmpeg_path

CONCAT_OUTPUT_DIR = os.path.join("output", "playground", "videos")


class ConcatRequest(BaseModel):
    video_paths: List[str]


def concat_media(request: ConcatRequest, _user=Depends(auth.require_login)):
    """Concatenate a list of playground-generated video clips, in order,
    into one file. Used by the video-workflow feature to combine shots."""
    if not request.video_paths:
        raise HTTPException(status_code=400, detail="video_paths must not be empty")

    resolved: List[str] = []
    for p in request.video_paths:
        abs_path = resolve_local_media_path(p)
        if abs_path is None or not os.path.isfile(abs_path):
            raise HTTPException(status_code=400, detail=f"Invalid or missing video path: {p}")
        resolved.append(abs_path)

    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        raise HTTPException(status_code=500, detail="ffmpeg is not available on this server")

    try:
        output_path = concat_videos(resolved, ffmpeg_path=ffmpeg_path, output_dir=CONCAT_OUTPUT_DIR)
    except ConcatError as e:
        logger.error(f"[CONCAT] {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"path": to_posix_media_path(output_path)}


router.add_api_route("/concat", concat_media, methods=["POST"])
```

Add `from pydantic import BaseModel` to the top-of-file imports if not already present (check line 1-32 first — `GenerateRequest` etc. are likely defined in `.models` using pydantic already, so `BaseModel` may need importing directly here, or `ConcatRequest` can instead be added to `src/apps/playground/models.py` alongside the other request models — follow whichever pattern the existing `EstimateCostRequest`/`SaveToLibraryRequest` use in `models.py` and put `ConcatRequest` there instead for consistency, importing it in the `from .models import (...)` block at the top of `api.py`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_playground_concat_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/apps/playground/api.py src/apps/playground/models.py tests/test_playground_concat_api.py
git commit -m "feat(playground): add POST /playground/concat endpoint"
```

---

### Task 3: Frontend `playgroundApi.concat()` client

**Files:**
- Modify: `frontend/src/lib/api.ts` (add one interface + one method to the existing `playgroundApi` object, right after `deleteTemplate` or near `uploadMedia`/`uploadVideo` at line ~1804-1819)

**Interfaces:**
- Consumes: nothing new (uses `axios`, `API_URL` already imported/defined at the top of this file).
- Produces: `playgroundApi.concat(videoPaths: string[]) -> Promise<{ path: string }>` — Task 5's `VideoWorkflowPage.tsx` calls this on "Combine into final video".

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/__tests__/playground-api-concat.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';

vi.mock('axios');

describe('playgroundApi.concat', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  it('posts video_paths and returns the combined path', async () => {
    (axios.post as any).mockResolvedValue({ data: { path: 'playground/videos/workflow_abc.mp4' } });
    const { playgroundApi } = await import('@/lib/api');

    const result = await playgroundApi.concat(['playground/videos/a.mp4', 'playground/videos/b.mp4']);

    expect(result).toEqual({ path: 'playground/videos/workflow_abc.mp4' });
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/playground/concat'),
      { video_paths: ['playground/videos/a.mp4', 'playground/videos/b.mp4'] },
    );
  });
});
```

Check how existing tests in `frontend/src/__tests__/` mock `axios` for this file (`grep -n "vi.mock('axios')" frontend/src/__tests__/*.ts`) before assuming the shape above is exactly right — match whatever mocking convention is already established there instead of introducing a second one.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- playground-api-concat` (from `frontend/`)
Expected: FAIL — `playgroundApi.concat is not a function`

- [ ] **Step 3: Write the implementation**

Add to `frontend/src/lib/api.ts`, inside the `playgroundApi` object:

```ts
  concat: (videoPaths: string[]) =>
    axios.post<{ path: string }>(API_URL + "/playground/concat", { video_paths: videoPaths }).then(r => r.data),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- playground-api-concat` (from `frontend/`)
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/__tests__/playground-api-concat.test.ts
git commit -m "feat(frontend): add playgroundApi.concat client method"
```

---

### Task 4: `useShotSequenceStore` — shot array + mode inference

**Files:**
- Create: `frontend/src/components/modules/videoworkflow/useShotSequenceStore.ts`
- Test: `frontend/src/__tests__/shot-sequence-store.test.ts`

**Interfaces:**
- Consumes: `PlaygroundMode` type from `../playground/usePlaygroundStore` (already exported — `export type PlaygroundMode = 't2i' | 'i2i' | 't2v' | 'i2v' | 'r2v' | 'v2v';`). Only `'t2v' | 'i2v' | 'r2v' | 'v2v'` are ever produced by this store.
- Produces (consumed by Task 5's `ShotCard.tsx`/`VideoWorkflowPage.tsx` and Task 6's `useShotGeneration.ts`):
  ```ts
  export type ShotStatus = 'idle' | 'queued' | 'processing' | 'completed' | 'failed';

  export interface Shot {
    id: string;
    prompt: string;
    media: string[];         // image paths (0..9), or exactly one video path
    mediaType: 'image' | 'video' | null;
    status: ShotStatus;
    generationId?: string;
    outputPath?: string;
    error?: string;
  }

  export function inferShotMode(shot: Pick<Shot, 'media' | 'mediaType'>): 'r2v' | 'i2v' | 'v2v' | 't2v';

  export const MAX_SHOTS = 10;

  export interface ShotSequenceState {
    shots: Shot[];
    addShot: (atIndex?: number) => void;   // no-op if shots.length >= MAX_SHOTS
    removeShot: (id: string) => void;
    moveShot: (id: string, toIndex: number) => void;
    updateShotPrompt: (id: string, prompt: string) => void;
    setShotMedia: (id: string, media: string[], mediaType: 'image' | 'video' | null) => void;
    setShotStatus: (id: string, status: ShotStatus, patch?: Partial<Pick<Shot, 'generationId' | 'outputPath' | 'error'>>) => void;
    reset: () => void;
  }

  export const useShotSequenceStore: import('zustand').UseBoundStore<import('zustand').StoreApi<ShotSequenceState>>;
  ```

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/src/__tests__/shot-sequence-store.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { inferShotMode, useShotSequenceStore, MAX_SHOTS } from '@/components/modules/videoworkflow/useShotSequenceStore';

describe('inferShotMode', () => {
  it('returns t2v for no media', () => {
    expect(inferShotMode({ media: [], mediaType: null })).toBe('t2v');
  });

  it('returns i2v for exactly one image', () => {
    expect(inferShotMode({ media: ['a.png'], mediaType: 'image' })).toBe('i2v');
  });

  it('returns r2v for two or more images', () => {
    expect(inferShotMode({ media: ['a.png', 'b.png'], mediaType: 'image' })).toBe('r2v');
    expect(inferShotMode({ media: ['a.png', 'b.png', 'c.png'], mediaType: 'image' })).toBe('r2v');
  });

  it('returns v2v when mediaType is video, regardless of media array length', () => {
    expect(inferShotMode({ media: ['a.mp4'], mediaType: 'video' })).toBe('v2v');
  });
});

describe('useShotSequenceStore', () => {
  beforeEach(() => {
    useShotSequenceStore.getState().reset();
  });

  it('starts with one empty shot', () => {
    expect(useShotSequenceStore.getState().shots).toHaveLength(1);
    expect(useShotSequenceStore.getState().shots[0].status).toBe('idle');
  });

  it('addShot appends by default', () => {
    useShotSequenceStore.getState().addShot();
    expect(useShotSequenceStore.getState().shots).toHaveLength(2);
  });

  it('addShot inserts at the given index', () => {
    const { addShot } = useShotSequenceStore.getState();
    addShot(); // now 2 shots, indices 0,1
    const firstId = useShotSequenceStore.getState().shots[0].id;
    const secondId = useShotSequenceStore.getState().shots[1].id;
    addShot(1); // insert between them
    const ids = useShotSequenceStore.getState().shots.map((s) => s.id);
    expect(ids[0]).toBe(firstId);
    expect(ids[2]).toBe(secondId);
    expect(ids).toHaveLength(3);
  });

  it('addShot is a no-op at MAX_SHOTS', () => {
    const { addShot } = useShotSequenceStore.getState();
    for (let i = 0; i < MAX_SHOTS + 5; i++) addShot();
    expect(useShotSequenceStore.getState().shots.length).toBe(MAX_SHOTS);
  });

  it('removeShot removes by id', () => {
    const { addShot, removeShot } = useShotSequenceStore.getState();
    addShot();
    const idToRemove = useShotSequenceStore.getState().shots[0].id;
    removeShot(idToRemove);
    expect(useShotSequenceStore.getState().shots.find((s) => s.id === idToRemove)).toBeUndefined();
  });

  it('moveShot reorders', () => {
    const { addShot, moveShot } = useShotSequenceStore.getState();
    addShot();
    addShot();
    const ids = useShotSequenceStore.getState().shots.map((s) => s.id);
    moveShot(ids[0], 2);
    const newIds = useShotSequenceStore.getState().shots.map((s) => s.id);
    expect(newIds).toEqual([ids[1], ids[2], ids[0]]);
  });

  it('updateShotPrompt and setShotMedia update the right shot only', () => {
    const { addShot, updateShotPrompt, setShotMedia } = useShotSequenceStore.getState();
    addShot();
    const [firstId, secondId] = useShotSequenceStore.getState().shots.map((s) => s.id);
    updateShotPrompt(firstId, 'a cat walking');
    setShotMedia(secondId, ['x.png', 'y.png'], 'image');

    const shots = useShotSequenceStore.getState().shots;
    expect(shots.find((s) => s.id === firstId)!.prompt).toBe('a cat walking');
    expect(shots.find((s) => s.id === secondId)!.media).toEqual(['x.png', 'y.png']);
    expect(shots.find((s) => s.id === firstId)!.media).toEqual([]);
  });

  it('setShotStatus patches status and extra fields', () => {
    const { setShotStatus } = useShotSequenceStore.getState();
    const id = useShotSequenceStore.getState().shots[0].id;
    setShotStatus(id, 'completed', { outputPath: 'playground/videos/out.mp4' });
    const shot = useShotSequenceStore.getState().shots.find((s) => s.id === id)!;
    expect(shot.status).toBe('completed');
    expect(shot.outputPath).toBe('playground/videos/out.mp4');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- shot-sequence-store` (from `frontend/`)
Expected: FAIL — module not found

- [ ] **Step 3: Write the implementation**

```ts
// frontend/src/components/modules/videoworkflow/useShotSequenceStore.ts
'use client';

import { create } from 'zustand';

// ---------------------------------------------------------------------------
// Shot sequence store — the multi-shot video workflow's own state.
//
// Deliberately independent of usePlaygroundStore: that store models one
// compose form (single mode/prompt/media), and its queue/pump machinery
// assumes one active request stream. A shot sequence is N independently
// retriable units, so this store keeps its own array instead of forcing
// that shape into the single-compose model.
// ---------------------------------------------------------------------------

export const MAX_SHOTS = 10;

export type ShotStatus = 'idle' | 'queued' | 'processing' | 'completed' | 'failed';

export interface Shot {
  id: string;
  prompt: string;
  media: string[];
  mediaType: 'image' | 'video' | null;
  status: ShotStatus;
  generationId?: string;
  outputPath?: string;
  error?: string;
}

/** Mode inference precedence: a video attachment always wins (v2v ignores
 *  extra images by design — see design doc's mode-inference table). */
export function inferShotMode(
  shot: Pick<Shot, 'media' | 'mediaType'>,
): 'r2v' | 'i2v' | 'v2v' | 't2v' {
  if (shot.mediaType === 'video') return 'v2v';
  if (shot.media.length >= 2) return 'r2v';
  if (shot.media.length === 1) return 'i2v';
  return 't2v';
}

function makeEmptyShot(): Shot {
  return {
    id: crypto.randomUUID(),
    prompt: '',
    media: [],
    mediaType: null,
    status: 'idle',
  };
}

export interface ShotSequenceState {
  shots: Shot[];
  addShot: (atIndex?: number) => void;
  removeShot: (id: string) => void;
  moveShot: (id: string, toIndex: number) => void;
  updateShotPrompt: (id: string, prompt: string) => void;
  setShotMedia: (id: string, media: string[], mediaType: 'image' | 'video' | null) => void;
  setShotStatus: (
    id: string,
    status: ShotStatus,
    patch?: Partial<Pick<Shot, 'generationId' | 'outputPath' | 'error'>>,
  ) => void;
  reset: () => void;
}

export const useShotSequenceStore = create<ShotSequenceState>((set, get) => ({
  shots: [makeEmptyShot()],

  addShot: (atIndex) => {
    const { shots } = get();
    if (shots.length >= MAX_SHOTS) return;
    const next = [...shots];
    const insertAt = atIndex === undefined ? next.length : Math.max(0, Math.min(atIndex, next.length));
    next.splice(insertAt, 0, makeEmptyShot());
    set({ shots: next });
  },

  removeShot: (id) => {
    set({ shots: get().shots.filter((s) => s.id !== id) });
  },

  moveShot: (id, toIndex) => {
    const shots = [...get().shots];
    const fromIndex = shots.findIndex((s) => s.id === id);
    if (fromIndex === -1) return;
    const [moved] = shots.splice(fromIndex, 1);
    const clampedTo = Math.max(0, Math.min(toIndex, shots.length));
    shots.splice(clampedTo, 0, moved);
    set({ shots });
  },

  updateShotPrompt: (id, prompt) => {
    set({ shots: get().shots.map((s) => (s.id === id ? { ...s, prompt } : s)) });
  },

  setShotMedia: (id, media, mediaType) => {
    set({ shots: get().shots.map((s) => (s.id === id ? { ...s, media, mediaType } : s)) });
  },

  setShotStatus: (id, status, patch) => {
    set({
      shots: get().shots.map((s) => (s.id === id ? { ...s, status, ...patch } : s)),
    });
  },

  reset: () => set({ shots: [makeEmptyShot()] }),
}));
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- shot-sequence-store` (from `frontend/`)
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/modules/videoworkflow/useShotSequenceStore.ts frontend/src/__tests__/shot-sequence-store.test.ts
git commit -m "feat(frontend): add useShotSequenceStore for multi-shot video workflow"
```

---

### Task 5: `useShotGeneration` — drive one shot through generate + poll

**Files:**
- Create: `frontend/src/components/modules/videoworkflow/useShotGeneration.ts`
- Test: `frontend/src/__tests__/shot-generation.test.ts`

**Interfaces:**
- Consumes: `playgroundApi.generate`, `playgroundApi.getGenerationStatus`, `playgroundApi.getGeneration` from `@/lib/api` (all already exist, same shapes `useGenerationRunner.ts` already uses); `useShotSequenceStore`, `Shot`, `inferShotMode` from Task 4.
- Produces: `useShotGeneration() -> { generateShot: (shot: Shot) => Promise<void> }`, consumed by Task 6's `VideoWorkflowPage.tsx`/`ShotCard.tsx` for both the per-shot Generate button and "Generate all".

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/__tests__/shot-generation.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  playgroundApi: {
    generate: vi.fn(),
    getGenerationStatus: vi.fn(),
    getGeneration: vi.fn(),
  },
}));

import { playgroundApi } from '@/lib/api';
import { useShotSequenceStore } from '@/components/modules/videoworkflow/useShotSequenceStore';
import { useShotGeneration } from '@/components/modules/videoworkflow/useShotGeneration';

function makeResponse(overrides: Partial<any> = {}) {
  return {
    id: 'gen-1',
    mode: 'i2v',
    model_id: 'model-x',
    prompt: 'a cat',
    negative_prompt: undefined,
    input_media: ['a.png'],
    parameters: {},
    batch_size: 1,
    outputs: [],
    status: 'processing',
    error: undefined,
    created_at: '2026-09-18T00:00:00Z',
    ...overrides,
  };
}

describe('useShotGeneration.generateShot', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useShotSequenceStore.getState().reset();
  });

  it('marks the shot processing, then completed with the output path on success', async () => {
    const shot = useShotSequenceStore.getState().shots[0];
    useShotSequenceStore.getState().updateShotPrompt(shot.id, 'a cat walking');
    useShotSequenceStore.getState().setShotMedia(shot.id, ['a.png'], 'image');

    (playgroundApi.generate as any).mockResolvedValue(makeResponse({ status: 'processing' }));
    (playgroundApi.getGenerationStatus as any).mockResolvedValue({ id: 'gen-1', status: 'completed', outputs: [], error: undefined });
    (playgroundApi.getGeneration as any).mockResolvedValue(
      makeResponse({
        status: 'completed',
        outputs: [{ id: 'out-1', media_path: 'playground/videos/out.mp4', media_type: 'video', saved_to_library: false }],
      }),
    );

    const { generateShot } = useShotGeneration();
    const updatedShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    await generateShot(updatedShot);

    const finalShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    expect(finalShot.status).toBe('completed');
    expect(finalShot.outputPath).toBe('playground/videos/out.mp4');
    expect(playgroundApi.generate).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'i2v', prompt: 'a cat walking', input_media: ['a.png'] }),
    );
  });

  it('marks the shot failed with the error message when generate rejects', async () => {
    const shot = useShotSequenceStore.getState().shots[0];
    useShotSequenceStore.getState().updateShotPrompt(shot.id, 'a dog running');

    (playgroundApi.generate as any).mockRejectedValue(new Error('quota exceeded'));

    const { generateShot } = useShotGeneration();
    const updatedShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    await generateShot(updatedShot);

    const finalShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    expect(finalShot.status).toBe('failed');
    expect(finalShot.error).toContain('quota exceeded');
  });

  it('marks the shot failed when the generation itself reaches status failed', async () => {
    const shot = useShotSequenceStore.getState().shots[0];
    useShotSequenceStore.getState().updateShotPrompt(shot.id, 'a bird flying');

    (playgroundApi.generate as any).mockResolvedValue(makeResponse({ status: 'processing' }));
    (playgroundApi.getGenerationStatus as any).mockResolvedValue({ id: 'gen-1', status: 'failed', outputs: [], error: 'model error' });
    (playgroundApi.getGeneration as any).mockResolvedValue(makeResponse({ status: 'failed', error: 'model error' }));

    const { generateShot } = useShotGeneration();
    const updatedShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    await generateShot(updatedShot);

    const finalShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    expect(finalShot.status).toBe('failed');
    expect(finalShot.error).toBe('model error');
  });
});
```

Check `frontend/src/__tests__/` for the existing `vi.mock('@/lib/api', ...)` convention (`grep -rln "vi.mock('@/lib/api'" frontend/src/__tests__/`) before finalizing this mock shape — reuse whatever pattern already exists there.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- shot-generation` (from `frontend/`)
Expected: FAIL — module not found

- [ ] **Step 3: Write the implementation**

```ts
// frontend/src/components/modules/videoworkflow/useShotGeneration.ts
'use client';

import { playgroundApi } from '@/lib/api';
import { useShotSequenceStore, inferShotMode, type Shot } from './useShotSequenceStore';

// ---------------------------------------------------------------------------
// Drives ONE shot from "generate pressed" to a terminal status.
//
// A thin, shot-scoped sibling of playground/useGenerationRunner.ts —
// deliberately not shared. That hook's queue/pump model exists to throttle
// one compose form's rapid-fire requests against maxConcurrent; here, each
// shot already IS one bounded, independently-retriable unit, and "Generate
// all" is just N calls to this function. Reusing the pump would mean routing
// N independent shots through a single-compose queue that has no notion of
// "which shot does this generation belong to."
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 10 * 60 * 1000;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export interface ShotGenerationRunner {
  generateShot: (shot: Shot) => Promise<void>;
}

export function useShotGeneration(): ShotGenerationRunner {
  const setShotStatus = useShotSequenceStore((s) => s.setShotStatus);

  const generateShot = async (shot: Shot) => {
    if (!shot.prompt.trim()) return;

    setShotStatus(shot.id, 'queued');
    const mode = inferShotMode(shot);

    let generationId: string;
    try {
      const resp = await playgroundApi.generate({
        mode,
        model_id: '',
        prompt: shot.prompt.trim(),
        input_media: shot.media.length > 0 ? shot.media : undefined,
      });
      generationId = resp.id;
      setShotStatus(shot.id, 'processing', { generationId });

      if (resp.status === 'completed' || resp.status === 'failed') {
        finalize(shot.id, resp.status, resp.outputs, resp.error);
        return;
      }
    } catch (err) {
      setShotStatus(shot.id, 'failed', { error: err instanceof Error ? err.message : String(err) });
      return;
    }

    const deadline = Date.now() + POLL_TIMEOUT_MS;
    while (Date.now() < deadline) {
      await sleep(POLL_INTERVAL_MS);
      try {
        const statusResp = await playgroundApi.getGenerationStatus(generationId);
        if (statusResp.status === 'completed' || statusResp.status === 'failed') {
          const full = await playgroundApi.getGeneration(generationId);
          finalize(shot.id, full.status as 'completed' | 'failed', full.outputs, full.error);
          return;
        }
      } catch (err) {
        setShotStatus(shot.id, 'failed', { error: err instanceof Error ? err.message : String(err) });
        return;
      }
    }

    setShotStatus(shot.id, 'failed', { error: 'Generation timed out' });
  };

  function finalize(
    shotId: string,
    status: 'completed' | 'failed',
    outputs: Array<{ media_path: string }>,
    error?: string,
  ) {
    if (status === 'failed') {
      setShotStatus(shotId, 'failed', { error: error || 'Generation failed' });
      return;
    }
    const outputPath = outputs[0]?.media_path;
    if (!outputPath) {
      setShotStatus(shotId, 'failed', { error: 'Generation completed with no output' });
      return;
    }
    setShotStatus(shotId, 'completed', { outputPath });
  }

  return { generateShot };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- shot-generation` (from `frontend/`)
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/modules/videoworkflow/useShotGeneration.ts frontend/src/__tests__/shot-generation.test.ts
git commit -m "feat(frontend): add useShotGeneration to drive per-shot generate+poll"
```

---

### Task 6: i18n messages for the video workflow page

**Files:**
- Modify: `frontend/messages/en.json`, `frontend/messages/zh.json`, `frontend/messages/zh-Hant.json`

**Interfaces:**
- Produces: `nav.videoworkflow` key (consumed by Task 7's `GlobalSidebar.tsx`); `playground.videoWorkflow.*` keys (consumed by Task 8's `ShotCard.tsx`/`VideoWorkflowPage.tsx`) — exact key list below, all three files must define the same keys.

- [ ] **Step 1: Add the `nav` key**

In all three files, inside the existing `"nav": { ... }` block (zh-Hant example is at line 423-433 shown above), add one line after `"imagegen"`:

zh-Hant.json:
```json
    "videoworkflow": "多鏡頭工作流",
```

zh.json (mirror the existing zh entries' simplified wording — check the file for its `imagegen` value and match that register):
```json
    "videoworkflow": "多镜头工作流",
```

en.json:
```json
    "videoworkflow": "Video Workflow",
```

- [ ] **Step 2: Add the `playground.videoWorkflow` block**

In all three files, inside the existing `"playground": { ... }` block, add a new top-level key alongside `header`/`compose`/`mode`/`videoTab` (after the `videoTab` block, e.g. after zh-Hant.json line 976):

zh-Hant.json:
```json
    "videoWorkflow": {
      "pageTitle": "多鏡頭工作流",
      "pageSubtitle": "組合多個鏡頭，一次生成完整影片",
      "shotLabel": "鏡頭 {index}",
      "promptPlaceholder": "描述這個鏡頭的畫面，輸入 @ 可插入素材庫圖片",
      "pickFromLibrary": "從素材庫選取",
      "addShot": "新增鏡頭",
      "insertShotHere": "在此插入鏡頭",
      "removeShot": "刪除鏡頭",
      "generateShot": "生成此鏡頭",
      "generateAll": "全部生成",
      "combineButton": "合成完整影片",
      "combining": "合成中…",
      "combineSuccess": "合成完成",
      "combineFailed": "合成失敗",
      "combineRequiresAllCompleted": "所有鏡頭都完成生成後才能合成",
      "statusIdle": "尚未生成",
      "statusQueued": "已加入佇列",
      "statusProcessing": "生成中…",
      "statusCompleted": "已完成",
      "statusFailed": "生成失敗",
      "maxShotsReached": "已達鏡頭數量上限（{max}）"
    }
```

zh.json (simplified-Chinese equivalents of the above — mirror the existing register in that file's other `playground.*` strings):
```json
    "videoWorkflow": {
      "pageTitle": "多镜头工作流",
      "pageSubtitle": "组合多个镜头，一次生成完整影片",
      "shotLabel": "镜头 {index}",
      "promptPlaceholder": "描述这个镜头的画面，输入 @ 可插入素材库图片",
      "pickFromLibrary": "从素材库选取",
      "addShot": "新增镜头",
      "insertShotHere": "在此插入镜头",
      "removeShot": "删除镜头",
      "generateShot": "生成此镜头",
      "generateAll": "全部生成",
      "combineButton": "合成完整影片",
      "combining": "合成中…",
      "combineSuccess": "合成完成",
      "combineFailed": "合成失败",
      "combineRequiresAllCompleted": "所有镜头都完成生成后才能合成",
      "statusIdle": "尚未生成",
      "statusQueued": "已加入队列",
      "statusProcessing": "生成中…",
      "statusCompleted": "已完成",
      "statusFailed": "生成失败",
      "maxShotsReached": "已达镜头数量上限（{max}）"
    }
```

en.json:
```json
    "videoWorkflow": {
      "pageTitle": "Video Workflow",
      "pageSubtitle": "Compose multiple shots into one finished video",
      "shotLabel": "Shot {index}",
      "promptPlaceholder": "Describe this shot. Type @ to insert an image from your library.",
      "pickFromLibrary": "Pick from library",
      "addShot": "Add shot",
      "insertShotHere": "Insert shot here",
      "removeShot": "Remove shot",
      "generateShot": "Generate this shot",
      "generateAll": "Generate all",
      "combineButton": "Combine into final video",
      "combining": "Combining…",
      "combineSuccess": "Combined successfully",
      "combineFailed": "Combine failed",
      "combineRequiresAllCompleted": "All shots must complete generation before combining",
      "statusIdle": "Not generated",
      "statusQueued": "Queued",
      "statusProcessing": "Generating…",
      "statusCompleted": "Completed",
      "statusFailed": "Failed",
      "maxShotsReached": "Maximum of {max} shots reached"
    }
```

- [ ] **Step 3: Validate JSON syntax**

Run: `node -e "JSON.parse(require('fs').readFileSync('frontend/messages/en.json'))" && node -e "JSON.parse(require('fs').readFileSync('frontend/messages/zh.json'))" && node -e "JSON.parse(require('fs').readFileSync('frontend/messages/zh-Hant.json'))"`
Expected: no output, no error (a syntax error throws and prints a stack trace)

- [ ] **Step 4: Run the existing i18n consistency test**

Run: `npm test -- i18n` (from `frontend/`) — this repo already has `frontend/src/__tests__/i18n.test.ts`, which likely checks that all locale files define the same key set. Confirm it passes with the new keys added identically to all three files.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/messages/en.json frontend/messages/zh.json frontend/messages/zh-Hant.json
git commit -m "feat(i18n): add video workflow strings to en/zh/zh-Hant messages"
```

---

### Task 7: Sidebar entry + hash route wiring

**Files:**
- Modify: `frontend/src/components/layout/GlobalSidebar.tsx`
- Modify: `frontend/src/app/page.tsx`
- Test: `frontend/src/components/layout/__tests__/GlobalSidebar.spec.tsx` (existing file — extend it)

**Interfaces:**
- Consumes: nothing new.
- Produces: `GlobalTab` now includes `"videoworkflow"`; navigating to `#/video-workflow` sets `currentView` to `'videoworkflow'` and `activeTab` to `'videoworkflow'`, which Task 8 relies on for its `renderContent()` branch.

- [ ] **Step 1: Write the failing test**

Open `frontend/src/components/layout/__tests__/GlobalSidebar.spec.tsx` first and match its existing test style exactly (it already tests clicking `videogen`/`imagegen` nav items per the earlier `grep` results). Add one test following the same pattern:

```tsx
  it('navigates to the video workflow hash when the video workflow nav item is clicked', () => {
    const onTabChange = vi.fn();
    render(<GlobalSidebar activeTab="workspace" onTabChange={onTabChange} />);

    fireEvent.click(screen.getByText('多鏡頭工作流')); // or the translated label your test setup's i18n mock resolves to — match how the existing videogen/imagegen tests find their button text

    expect(onTabChange).toHaveBeenCalledWith('videoworkflow');
    expect(window.location.hash).toBe('#/video-workflow');
  });
```

Look at the existing `videogen`/`imagegen` test cases in this same file for the exact `render`/`fireEvent`/i18n-mock setup before writing this — copy their structure rather than guessing it, since this file's test harness conventions (how `useTranslations` is mocked, whether `window.location.hash` is reset in `beforeEach`) are already established there.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:ui -- GlobalSidebar` (from `frontend/` — this is a DOM/component test, so it uses `test:ui`, not `test`)
Expected: FAIL — no nav item matches

- [ ] **Step 3: Write the implementation**

In `frontend/src/components/layout/GlobalSidebar.tsx`:

```ts
export type GlobalTab = "workspace" | "library" | "videogen" | "videoworkflow" | "imagegen" | "history" | "settings";
```

```ts
export const GLOBAL_NAV_ITEMS: { id: GlobalTab; icon: typeof LayoutGrid; hash: string }[] = [
  { id: "workspace", icon: LayoutGrid, hash: "#/" },
  { id: "library", icon: Layers, hash: "#/library" },
  { id: "videogen", icon: Clapperboard, hash: "#/video-gen" },
  { id: "videoworkflow", icon: Film, hash: "#/video-workflow" },
  { id: "imagegen", icon: ImagePlus, hash: "#/image-gen" },
  { id: "history", icon: Clock, hash: "#/history" },
  { id: "settings", icon: Settings, hash: "#/settings" },
];
```

Add `Film` to the `lucide-react` import at the top of the file:
```ts
import { LayoutGrid, Layers, Clapperboard, Film, ImagePlus, Clock, Settings, LogOut, Gauge } from "lucide-react";
```

In `frontend/src/app/page.tsx`:

Find the `currentView` state declaration (line 465, shown earlier) and add `'videoworkflow'` to its union:
```ts
const [currentView, setCurrentView] = useState<'home' | 'project' | 'series' | 'series-episode' | 'library' | 'settings' | 'videogen' | 'videoworkflow' | 'imagegen' | 'history'>('home');
```

In the hash-router `useEffect` (around line 608-615, the `#/video-gen` block), add a new branch right after it:
```ts
      if (hash === '#/video-workflow') {
        setCurrentView('videoworkflow');
        setActiveTab('videoworkflow');
        setProjectId(null);
        setSeriesId(null);
        setEpisodeId(null);
        return;
      }
```

In `renderContent()` (around line 693, the `if (currentView === 'videogen')` block), add:
```ts
    if (currentView === 'videoworkflow') {
      return <VideoWorkflowPage />;
    }
```

Add the import near the top of `page.tsx`, alongside the existing `VideoGenPage`/`ImageGenPage` imports:
```ts
import VideoWorkflowPage from '@/components/modules/videoworkflow/VideoWorkflowPage';
```

(This import will not resolve until Task 8 creates the file — that's expected; Task 7's own test only exercises `GlobalSidebar.tsx` in isolation. If your toolchain runs a build/typecheck step before test:ui, add a `// TODO(task-8)` placeholder export in a stub `VideoWorkflowPage.tsx` file now, or simply do Task 7 and Task 8 in the same commit — see the note in Task 8.)

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test:ui -- GlobalSidebar` (from `frontend/`)
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/GlobalSidebar.tsx frontend/src/components/layout/__tests__/GlobalSidebar.spec.tsx frontend/src/app/page.tsx
git commit -m "feat(frontend): wire video workflow nav entry and hash route"
```

**Note:** If `page.tsx`'s import of `VideoWorkflowPage` breaks the frontend build before Task 8 exists, do Tasks 7 and 8 as one combined commit instead of two — the subagent executing this plan should check `npm run build` (or equivalent) after Task 7's Step 4 and, if it fails solely due to the missing `VideoWorkflowPage` module, proceed directly into Task 8 before committing either.

---

### Task 8: `ShotCard` component

**Files:**
- Create: `frontend/src/components/modules/videoworkflow/ShotCard.tsx`
- Test: `frontend/src/components/modules/videoworkflow/__tests__/ShotCard.spec.tsx`

**Interfaces:**
- Consumes: `Shot`, `ShotStatus`, `useShotSequenceStore` from Task 4; `useShotGeneration` from Task 5; `AssetSourcePicker` from `../playground/AssetSourcePicker` (existing, props-only component: `{ isOpen, onClose, onSelect: (path, hasGridOverlay?) => void, accept: 'image' | 'video' | 'all' }`); `mediaUrl` from `@/lib/mediaPath` (existing, used by `MediaInput.tsx`).
- Produces: `<ShotCard shot={Shot} index={number} onRemove={() => void} />`, consumed by Task 9's `VideoWorkflowPage.tsx`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/modules/videoworkflow/__tests__/ShotCard.spec.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  playgroundApi: {
    generate: vi.fn().mockResolvedValue({ id: 'g1', status: 'processing', outputs: [] }),
    getGenerationStatus: vi.fn(),
    getGeneration: vi.fn(),
  },
}));

import ShotCard from '../ShotCard';
import { useShotSequenceStore } from '../useShotSequenceStore';

describe('ShotCard', () => {
  beforeEach(() => {
    useShotSequenceStore.getState().reset();
  });

  it('renders the prompt textarea and updates the store on change', () => {
    const shot = useShotSequenceStore.getState().shots[0];
    render(<ShotCard shot={shot} index={0} onRemove={() => {}} />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'a robot dancing' } });

    expect(useShotSequenceStore.getState().shots[0].prompt).toBe('a robot dancing');
  });

  it('calls onRemove when the remove button is clicked', () => {
    const shot = useShotSequenceStore.getState().shots[0];
    const onRemove = vi.fn();
    render(<ShotCard shot={shot} index={0} onRemove={onRemove} />);

    fireEvent.click(screen.getByLabelText(/remove|刪除|删除/i));
    expect(onRemove).toHaveBeenCalled();
  });

  it('disables the generate button when the prompt is empty', () => {
    const shot = useShotSequenceStore.getState().shots[0];
    render(<ShotCard shot={shot} index={0} onRemove={() => {}} />);

    const generateButton = screen.getByRole('button', { name: /generate|生成/i });
    expect(generateButton).toBeDisabled();
  });
});
```

Check `frontend/src/components/modules/playground/__tests__/MediaInput.assetSource.spec.tsx` first for this repo's exact `render`/`vi.mock`/`useTranslations` mocking conventions for a component that uses `AssetSourcePicker` — copy its setup boilerplate (test providers, i18n mock, etc.) rather than reinventing it, since `ShotCard` uses the same picker.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:ui -- ShotCard` (from `frontend/`)
Expected: FAIL — module not found

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/src/components/modules/videoworkflow/ShotCard.tsx
'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { ImagePlus, Film, X, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { mediaUrl } from '@/lib/mediaPath';
import AssetSourcePicker, { type AssetSource } from '../playground/AssetSourcePicker';
import { useShotSequenceStore, type Shot } from './useShotSequenceStore';
import { useShotGeneration } from './useShotGeneration';

function isVideoPath(path: string): boolean {
  return /\.(mp4|mov|webm|avi|mkv)$/i.test(path);
}

function resolveMediaSrc(path: string): string {
  if (/^(https?:|blob:|data:|\/)/i.test(path)) return path;
  return mediaUrl(path);
}

const MAX_IMAGES = 9;

export default function ShotCard({
  shot,
  index,
  onRemove,
}: {
  shot: Shot;
  index: number;
  onRemove: () => void;
}) {
  const t = useTranslations('playground.videoWorkflow');
  const updateShotPrompt = useShotSequenceStore((s) => s.updateShotPrompt);
  const setShotMedia = useShotSequenceStore((s) => s.setShotMedia);
  const { generateShot } = useShotGeneration();
  const [showPicker, setShowPicker] = useState(false);

  const canAddMoreImages = shot.mediaType !== 'video' && shot.media.length < MAX_IMAGES;
  const canGenerate = shot.prompt.trim().length > 0 && shot.status !== 'queued' && shot.status !== 'processing';

  const handleAssetSelect = (path: string) => {
    const asVideo = isVideoPath(path);
    if (asVideo) {
      setShotMedia(shot.id, [path], 'video');
    } else {
      const nextMedia = shot.mediaType === 'image' ? [...shot.media, path] : [path];
      setShotMedia(shot.id, nextMedia, 'image');
    }
    setShowPicker(false);
  };

  const handleRemoveMedia = (mediaIndex: number) => {
    const nextMedia = shot.media.filter((_, i) => i !== mediaIndex);
    setShotMedia(shot.id, nextMedia, nextMedia.length > 0 ? shot.mediaType : null);
  };

  const handlePromptChange = (value: string) => {
    updateShotPrompt(shot.id, value);
    if (value.endsWith('@')) {
      setShowPicker(true);
    }
  };

  const pickerAccept: AssetSource extends never ? never : 'image' | 'video' | 'all' = 'all';

  return (
    <div className="glass-panel atelier-card rounded-[20px] px-5 py-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[0.6875rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
          {t('shotLabel', { index: index + 1 })}
        </span>
        <button type="button" aria-label={t('removeShot')} onClick={onRemove} className="text-text-muted hover:text-foreground">
          <X className="w-4 h-4" />
        </button>
      </div>

      <textarea
        value={shot.prompt}
        onChange={(e) => handlePromptChange(e.target.value)}
        placeholder={t('promptPlaceholder')}
        rows={3}
        className="w-full rounded-[12px] border border-border-subtle bg-input-bg px-3 py-2 text-sm text-foreground placeholder:text-text-muted focus:outline-none focus:border-primary"
      />

      <div className="flex flex-wrap gap-2">
        {shot.media.map((path, i) => (
          <div key={path + i} className="group relative w-20 h-20 rounded-[12px] overflow-hidden bg-elevated border border-border-subtle">
            {isVideoPath(path) ? (
              <video src={resolveMediaSrc(path)} className="w-full h-full object-cover" muted />
            ) : (
              <img src={resolveMediaSrc(path)} alt="" className="w-full h-full object-cover" />
            )}
            <button
              type="button"
              onClick={() => handleRemoveMedia(i)}
              className="absolute top-1 right-1 w-4 h-4 rounded-full bg-black/70 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        ))}

        {canAddMoreImages && (
          <button
            type="button"
            onClick={() => setShowPicker(true)}
            className="w-20 h-20 rounded-[12px] bg-input-bg border border-dashed border-border-subtle flex items-center justify-center text-text-muted hover:text-foreground hover:border-foreground/30 hover:bg-hover-bg transition-colors"
          >
            {shot.mediaType === 'video' ? <Film className="w-5 h-5" /> : <ImagePlus className="w-5 h-5" />}
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={() => setShowPicker(true)}
        className="self-start text-xs text-text-secondary hover:text-foreground underline"
      >
        {t('pickFromLibrary')}
      </button>

      <AssetSourcePicker isOpen={showPicker} onClose={() => setShowPicker(false)} onSelect={handleAssetSelect} accept={pickerAccept} />

      <div className="flex items-center justify-between mt-1">
        <StatusBadge status={shot.status} error={shot.error} t={t} />
        <button
          type="button"
          onClick={() => generateShot(shot)}
          disabled={!canGenerate}
          className="rounded-full px-4 py-2 text-xs font-semibold bg-primary text-on-accent disabled:opacity-40 disabled:cursor-not-allowed hover:bg-primary-hover"
        >
          {t('generateShot')}
        </button>
      </div>
    </div>
  );
}

function StatusBadge({
  status,
  error,
  t,
}: {
  status: Shot['status'];
  error?: string;
  t: ReturnType<typeof useTranslations>;
}) {
  if (status === 'processing' || status === 'queued') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-text-secondary">
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> {t('statusProcessing')}
      </span>
    );
  }
  if (status === 'completed') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-status-completed-fg">
        <CheckCircle2 className="w-3.5 h-3.5" /> {t('statusCompleted')}
      </span>
    );
  }
  if (status === 'failed') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-status-failed-fg" title={error}>
        <AlertCircle className="w-3.5 h-3.5" /> {t('statusFailed')}
      </span>
    );
  }
  return <span className="text-xs text-text-muted">{t('statusIdle')}</span>;
}
```

Before finalizing, check `src/components/modules/playground/AssetSourcePicker.tsx`'s actual export shape (`export type AssetSource = ...` plus `export default function AssetSourcePicker`) — if `AssetSource` is not exported as shown in the file read earlier, drop the `pickerAccept` type-only line and just inline `accept="all"` in the JSX, since the type annotation is not load-bearing for the feature to work correctly, only for extra type safety.

Also verify `status-completed-fg` / `status-failed-fg` are real Tailwind/CSS custom classes already used elsewhere in `playground/` (they appeared in `MediaInput.tsx` earlier as `status-failed-fg`) — reuse whatever token names that file already established rather than inventing new ones.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test:ui -- ShotCard` (from `frontend/`)
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/modules/videoworkflow/ShotCard.tsx frontend/src/components/modules/videoworkflow/__tests__/ShotCard.spec.tsx
git commit -m "feat(frontend): add ShotCard component for multi-shot video workflow"
```

---

### Task 9: `VideoWorkflowPage` — page shell, generate all, combine

**Files:**
- Create: `frontend/src/components/modules/videoworkflow/VideoWorkflowPage.tsx`
- Test: `frontend/src/components/modules/videoworkflow/__tests__/VideoWorkflowPage.spec.tsx`

**Interfaces:**
- Consumes: `useShotSequenceStore`, `MAX_SHOTS` from Task 4; `useShotGeneration` from Task 5; `ShotCard` from Task 8; `playgroundApi.concat` from Task 3; `mediaUrl` from `@/lib/mediaPath`.
- Produces: `<VideoWorkflowPage />` default export — this is exactly what Task 7's `page.tsx` import expects.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/modules/videoworkflow/__tests__/VideoWorkflowPage.spec.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  playgroundApi: {
    generate: vi.fn(),
    getGenerationStatus: vi.fn(),
    getGeneration: vi.fn(),
    concat: vi.fn(),
  },
}));

import { playgroundApi } from '@/lib/api';
import VideoWorkflowPage from '../VideoWorkflowPage';
import { useShotSequenceStore, MAX_SHOTS } from '../useShotSequenceStore';

describe('VideoWorkflowPage', () => {
  beforeEach(() => {
    useShotSequenceStore.getState().reset();
  });

  it('renders one shot card initially and can add another', () => {
    render(<VideoWorkflowPage />);
    expect(screen.getAllByRole('textbox')).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: /add shot|新增鏡頭|新增镜头/i }));
    expect(screen.getAllByRole('textbox')).toHaveLength(2);
  });

  it('caps shots at MAX_SHOTS — the add button disables at the limit', () => {
    render(<VideoWorkflowPage />);
    const addButton = screen.getByRole('button', { name: /add shot|新增鏡頭|新增镜头/i });
    for (let i = 1; i < MAX_SHOTS; i++) fireEvent.click(addButton);

    expect(screen.getAllByRole('textbox')).toHaveLength(MAX_SHOTS);
    expect(addButton).toBeDisabled();
  });

  it('disables combine until every shot is completed, then calls concat with outputs in order', async () => {
    render(<VideoWorkflowPage />);
    const combineButton = screen.getByRole('button', { name: /combine|合成完整影片/i });
    expect(combineButton).toBeDisabled();

    // Simulate two completed shots directly via the store (unit-level assertion,
    // not exercising the full generate flow — that's useShotGeneration's own test).
    const [firstId] = useShotSequenceStore.getState().shots.map((s) => s.id);
    useShotSequenceStore.getState().addShot();
    const [, secondId] = useShotSequenceStore.getState().shots.map((s) => s.id);
    useShotSequenceStore.getState().setShotStatus(firstId, 'completed', { outputPath: 'playground/videos/a.mp4' });
    useShotSequenceStore.getState().setShotStatus(secondId, 'completed', { outputPath: 'playground/videos/b.mp4' });

    (playgroundApi.concat as any).mockResolvedValue({ path: 'playground/videos/workflow_final.mp4' });

    await waitFor(() => expect(combineButton).not.toBeDisabled());
    fireEvent.click(combineButton);

    await waitFor(() =>
      expect(playgroundApi.concat).toHaveBeenCalledWith(['playground/videos/a.mp4', 'playground/videos/b.mp4']),
    );
  });
});
```

Match this repo's existing conventions for testing a zustand-store-driven page component — check `frontend/src/components/modules/playground/__tests__/storeWiring.compose.spec.tsx` for how it renders a page against a live store instance (whether it wraps in a Provider or, like `useShotSequenceStore` here, relies on the store being a plain module-level singleton reset in `beforeEach`).

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:ui -- VideoWorkflowPage` (from `frontend/`)
Expected: FAIL — module not found

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/src/components/modules/videoworkflow/VideoWorkflowPage.tsx
'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, Sparkles, Film } from 'lucide-react';
import { playgroundApi } from '@/lib/api';
import { mediaUrl } from '@/lib/mediaPath';
import { useShotSequenceStore, MAX_SHOTS } from './useShotSequenceStore';
import { useShotGeneration } from './useShotGeneration';
import ShotCard from './ShotCard';

export default function VideoWorkflowPage() {
  const t = useTranslations('playground.videoWorkflow');
  const shots = useShotSequenceStore((s) => s.shots);
  const addShot = useShotSequenceStore((s) => s.addShot);
  const removeShot = useShotSequenceStore((s) => s.removeShot);
  const { generateShot } = useShotGeneration();

  const [combining, setCombining] = useState(false);
  const [combineError, setCombineError] = useState<string | null>(null);
  const [finalVideoPath, setFinalVideoPath] = useState<string | null>(null);

  const allCompleted = shots.length > 0 && shots.every((s) => s.status === 'completed');
  const atMax = shots.length >= MAX_SHOTS;

  const handleGenerateAll = () => {
    shots.filter((s) => s.status !== 'completed').forEach((s) => generateShot(s));
  };

  const handleCombine = async () => {
    setCombining(true);
    setCombineError(null);
    try {
      const outputPaths = shots.map((s) => s.outputPath!).filter(Boolean);
      const result = await playgroundApi.concat(outputPaths);
      setFinalVideoPath(result.path);
    } catch (err) {
      setCombineError(err instanceof Error ? err.message : String(err));
    } finally {
      setCombining(false);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto scrollbar-thin px-7 py-6">
      <header className="mb-5">
        <h1 className="atelier-display font-display text-[1.625rem] font-semibold tracking-tight text-foreground">
          {t('pageTitle')}
        </h1>
        <p className="text-sm text-text-secondary mt-1">{t('pageSubtitle')}</p>
      </header>

      <div className="flex flex-col gap-4 max-w-3xl">
        {shots.map((shot, index) => (
          <ShotCard key={shot.id} shot={shot} index={index} onRemove={() => removeShot(shot.id)} />
        ))}

        <button
          type="button"
          onClick={() => addShot()}
          disabled={atMax}
          className="flex items-center justify-center gap-2 rounded-[16px] border border-dashed border-border-subtle py-3 text-sm text-text-secondary hover:text-foreground hover:border-foreground/30 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Plus className="w-4 h-4" />
          {atMax ? t('maxShotsReached', { max: MAX_SHOTS }) : t('addShot')}
        </button>
      </div>

      <div className="sticky bottom-0 mt-6 -mx-7 border-t border-glass-border bg-surface/80 backdrop-blur-md px-7 py-4 flex items-center gap-3 max-w-3xl">
        <button
          type="button"
          onClick={handleGenerateAll}
          className="inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold bg-elevated text-foreground hover:bg-hover-bg"
        >
          <Sparkles className="w-4 h-4" />
          {t('generateAll')}
        </button>

        <button
          type="button"
          onClick={handleCombine}
          disabled={!allCompleted || combining}
          title={!allCompleted ? t('combineRequiresAllCompleted') : undefined}
          className="inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold bg-primary text-on-accent disabled:opacity-40 disabled:cursor-not-allowed hover:bg-primary-hover"
        >
          <Film className="w-4 h-4" />
          {combining ? t('combining') : t('combineButton')}
        </button>

        {combineError && <span className="text-xs text-status-failed-fg">{t('combineFailed')}: {combineError}</span>}
      </div>

      {finalVideoPath && (
        <div className="mt-4 max-w-3xl">
          <video src={mediaUrl(finalVideoPath)} controls className="w-full rounded-[16px]" />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test:ui -- VideoWorkflowPage` (from `frontend/`)
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/modules/videoworkflow/VideoWorkflowPage.tsx frontend/src/components/modules/videoworkflow/__tests__/VideoWorkflowPage.spec.tsx
git commit -m "feat(frontend): add VideoWorkflowPage combining shot cards, generate-all, and concat"
```

---

### Task 10: Manual/Playwright end-to-end verification

**Files:** none (verification only, per this workspace's CLAUDE.md L2/L3 rules for UI changes)

- [ ] **Step 1: Start the dev server**

Run whatever this repo's `run` skill or `dev.bat`/`npm run dev` uses to launch the full stack (frontend + backend) locally.

- [ ] **Step 2: Navigate to the new page**

Open the app, log in, click the new "Video Workflow" (多鏡頭工作流) sidebar entry, confirm the URL becomes `#/video-workflow` and one empty shot card renders.

- [ ] **Step 3: Build a 2-shot sequence with mixed media**

Shot 1: type a prompt only (no media) — confirm it would run as t2v (no visible mode label, per the design's "never show mode names" rule — just confirm the Generate button enables once the prompt is non-empty).
Shot 2: click "Pick from library", select one image, add a second image via "add more" — confirm both thumbnails render and the shot accepts a second image (r2v case).

- [ ] **Step 4: Generate all, watch status transitions**

Click "Generate all". Confirm each shot's status badge moves idle → queued/processing → completed (or failed, with the error surfaced) independently, and the page doesn't block on one shot while another is still running.

- [ ] **Step 5: Combine and verify playback order**

Once both shots show completed, confirm "Combine into final video" becomes enabled, click it, wait for the result `<video>` to appear, and play it — confirm shot 1's content plays before shot 2's (order preserved), per the spec's core guarantee.

- [ ] **Step 6: Take a screenshot for the record**

Per this workspace's CLAUDE.md screenshot rule, save to the workspace's `screenshot/` directory or this task's scratchpad — not the repo root.

- [ ] **Step 7: Commit any fixes found during manual verification**

If Step 3-5 surface a bug, fix it, re-run the relevant automated test from whichever task owns that file, then commit the fix separately with a `fix(video-workflow): ...` message — do not silently patch without a corresponding test update if the bug reveals a gap the automated tests missed.

---

## Self-Review Notes

**Spec coverage:** shot add/insert-at-any-position (Task 4 `addShot(atIndex)`) · 10-shot cap (Task 4 `MAX_SHOTS`) · per-shot independent generate (Task 5/8) · mode auto-inference hidden from UI (Task 4 `inferShotMode`, never rendered in Task 8's `ShotCard`) · `@`-trigger + button both opening `AssetSourcePicker` (Task 8) · multi-image per shot (Task 8 thumbnail grid + "add more") · concat-only backend, no subtitles/BGM (Task 1) · sidebar/route additive wiring (Task 7) · manual E2E order verification (Task 10). No spec requirement without a task.

**Type consistency:** `Shot`/`ShotStatus`/`inferShotMode`/`MAX_SHOTS` defined once in Task 4, imported verbatim (not redefined) by Tasks 5, 8, 9. `playgroundApi.concat` defined once in Task 3, called only in Task 9. `ConcatError`/`concat_videos`/`VIDEO_OUTPUT_DIR`-equivalent (`CONCAT_OUTPUT_DIR`) defined once in Task 1, imported by Task 2.

**Known follow-ups intentionally left as plan notes, not silent gaps:**
- Task 2's test file has a placeholder `_auth_headers` fixture that must be wired to this repo's actual test-auth convention before the task is considered done — flagged explicitly in Step 1, not glossed over.
- Task 7 flags the cross-task import ordering risk (page.tsx importing a not-yet-created module) and gives the executing agent an explicit instruction for how to handle it.
- The local-upload gap in `MediaInput`/`AssetSourcePicker` (memory: `feedback_media_input_upload_removed_beyond_user_intent_2026-09-18.md`) is explicitly out of scope per the Global Constraints section — not forgotten, deliberately deferred to a separate session per the user's own instruction.
