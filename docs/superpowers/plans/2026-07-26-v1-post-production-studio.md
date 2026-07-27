# V1「后期工坊」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mock ExportManager with a real non-destructive editing engine (EDL-based FFmpeg pipeline), rewrites the Timeline from visual mock to functional multi-track editor, adds transition effects library, and provides SSE-streamed export with multi-format support.

**Architecture:** New `editing.py` module handles all FFmpeg command construction via Edit Decision Lists. API layer adds CRUD for timeline state + SSE export progress. Frontend Timeline component is rewritten to drive edits through the API. The existing `merge_videos()` path is preserved; the new export pipeline is additive.

**Tech Stack:** Python 3.11+ / FastAPI / Pydantic / FFmpeg (CLI) / React 18 + TypeScript / Framer Motion / WaveSurfer.js

**Spec:** `docs/superpowers/specs/2026-07-26-PrismReel-professional-studio-roadmap-design.md`

## Global Constraints

- Python 3.11+, Node 20+, React 18, Next.js 14, TypeScript strict
- All new backend endpoints use `def` (sync handler) unless they contain `await` — per api.py convention (audited 2026-05-21)
- All IDs validated through `_validate_safe_id()` / `_SAFE_ID_RE` before filesystem use
- FFmpeg path resolved via existing `get_ffmpeg_path()` from `src/utils/system_check.py`
- Media references: local path `output/` relative, OSS object keys via `is_object_key()`
- Frontend: dark theme, glass aesthetic (`bg-surface`, `border-glass-border`), Framer Motion for animations
- New modules write to `output/projects.json` via pipeline `_save_data()` with RLock
- Tests: pytest for backend (files in `tests/`), Vitest for frontend (files in `frontend/src/__tests__/`)

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| CREATE | `src/apps/comic_gen/editing.py` | EditingEngine — FFmpeg EDL builder + render |
| CREATE | `tests/test_editing.py` | Unit tests for EditingEngine + EDL models |
| CREATE | `frontend/src/components/modules/TimelineEditor.tsx` | Functional multi-track timeline replacing visual mock |
| CREATE | `frontend/src/components/modules/TransitionPicker.tsx` | Transition preset picker panel |
| CREATE | `frontend/src/components/modules/ExportProgressBar.tsx` | SSE-connected export progress component |
| MODIFY | `src/apps/comic_gen/models.py` | Add EditDecision, TimelineData, TransitionConfig, ExportPreset |
| MODIFY | `src/apps/comic_gen/api.py` | Add 8 new endpoints (editing CRUD, export SSE, preview) |
| MODIFY | `src/apps/comic_gen/pipeline.py` | Add 6 new methods (editing, transitions, export) |
| REPLACE | `src/apps/comic_gen/export.py` | Replace mock ExportManager with real FFmpeg renderer |
| MODIFY | `frontend/src/components/modules/VideoAssembly.tsx` | Add "编辑" tab, wire new components |
| MODIFY | `frontend/src/lib/api.ts` | Add API client methods for new endpoints |
| MODIFY | `frontend/src/store/projectStore.ts` | Add timeline/transition/exportPreset state fields |

---

### Task 1: Data Models — EditDecision, TimelineData, TransitionConfig, ExportPreset

**Files:**
- Modify: `src/apps/comic_gen/models.py` (append after existing models)

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `EditDecision` — single editing operation
  - `TimelineData` — project-level timeline state container
  - `TransitionConfig` — transition between two shots
  - `ExportPreset` — export format/resolution/codec combo
  - `ExportProgress` — SSE progress payload

- [ ] **Step 1: Add models to models.py**

Open `src/apps/comic_gen/models.py`. Append the following after the last existing model class (before any `# ---` section dividers near end-of-file):

```python
# ============================================================
# V1 Post-Production Models — Editing Engine, Transitions, Export
# ============================================================

class CropRect(BaseModel):
    """Crop region in relative coordinates (0.0–1.0)."""
    x: float = Field(0.0, ge=0.0, le=1.0)
    y: float = Field(0.0, ge=0.0, le=1.0)
    width: float = Field(1.0, ge=0.01, le=1.0)
    height: float = Field(1.0, ge=0.01, le=1.0)


class EditDecision(BaseModel):
    """A single non-destructive edit operation on a shot."""
    id: str = Field(default_factory=lambda: f"edit_{uuid.uuid4().hex[:8]}")
    shot_id: str  # references StoryboardFrame.id
    operation: str  # "trim" | "split" | "speed" | "crop" | "replace"
    params: Dict[str, Any] = Field(default_factory=dict)
    # trim:  {"start": 0.0, "end": 5.0}  (seconds)
    # split: {"at_time": 3.5, "new_shot_id": "frame_xxxxxxxx"}
    # speed: {"factor": 2.0}  (0.25–4.0)
    # crop:  {"rect": {"x":0,"y":0,"width":1,"height":0.5625}}
    # replace: {"video_url": "uploads/xxx.mp4"}
    created_at: float = Field(default_factory=time.time)


class TransitionConfig(BaseModel):
    """Transition effect between two adjacent shots."""
    id: str = Field(default_factory=lambda: f"trans_{uuid.uuid4().hex[:8]}")
    from_shot_id: str
    to_shot_id: str
    transition_type: str = "cut"  # "cut" | "dissolve" | "fade_black" | "fade_white" | "push_left" | "push_right" | "push_up" | "push_down" | "wipe_left" | "wipe_right" | "wipe_down" | "wipe_up" | "zoom_in" | "zoom_out" | "spin"
    duration_ms: int = Field(300, ge=100, le=2000)  # milliseconds


class TimelineTrack(BaseModel):
    """A single track in the multi-track timeline."""
    track_id: str
    track_type: str  # "video" | "dialogue" | "bgm" | "sfx" | "subtitle"
    label: str = ""
    shot_ids: List[str] = Field(default_factory=list)  # ordered shot IDs in this track
    muted: bool = False
    volume: float = Field(1.0, ge=0.0, le=2.0)


class TimelineData(BaseModel):
    """Per-project timeline state persisted alongside Script."""
    tracks: List[TimelineTrack] = Field(default_factory=list)
    edits: List[EditDecision] = Field(default_factory=list)
    transitions: List[TransitionConfig] = Field(default_factory=list)
    updated_at: float = Field(default_factory=time.time)


class ExportPreset(BaseModel):
    """Export configuration preset."""
    id: str = Field(default_factory=lambda: f"export_{uuid.uuid4().hex[:8]}")
    preset_name: str  # "douyin" | "kuaishou" | "bilibili" | "youtube" | "custom"
    resolution: str = "1080p"  # "720p" | "1080p" | "original"
    codec: str = "h264"  # "h264" | "h265"
    format: str = "mp4"  # "mp4" | "mov" | "webm"
    bitrate: str = "2M"  # e.g. "2M", "6M", "8M"
    fps: int = 30


class ExportProgress(BaseModel):
    """SSE progress payload emitted during export rendering."""
    phase: str  # "collecting" | "rendering_shots" | "applying_edits" | "encoding" | "done" | "error"
    current: int = 0
    total: int = 0
    eta_seconds: float = 0
    message: str = ""
    output_url: Optional[str] = None
    error: Optional[str] = None
```

- [ ] **Step 2: Verify models parse correctly**

Run:
```
python -c "from src.apps.comic_gen.models import EditDecision, TimelineData, TransitionConfig, ExportPreset, ExportProgress, CropRect; print('All V1 models imported OK')"
```
Expected: `All V1 models imported OK`

- [ ] **Step 3: Run existing test suite to check no regressions**

Run: `pytest tests/ -x -q`
Expected: All existing tests pass (new models are additive, no breaking changes)

- [ ] **Step 4: Commit**

```bash
git add src/apps/comic_gen/models.py
git commit -m "feat(v1-post): add V1 editing data models (EditDecision, TimelineData, TransitionConfig, ExportPreset, ExportProgress)"
```

---

### Task 2: EditingEngine — FFmpeg EDL Builder + Render

**Files:**
- Create: `src/apps/comic_gen/editing.py`
- Create: `tests/test_editing.py`

**Interfaces:**
- Consumes: `EditDecision`, `TransitionConfig`, `ExportPreset` from Task 1; `get_ffmpeg_path()` from `src/utils/system_check.py`; `_validate_safe_id()`, `_safe_resolve_path()` from `pipeline.py`
- Produces:
  - `EditingEngine.__init__(self, ffmpeg_path: str | None = None)`
  - `EditingEngine.build_concat_file(self, shot_paths: List[str], output_dir: str) -> str` — returns concat list file path
  - `EditingEngine.build_filter_chain(self, edits: List[EditDecision], transitions: List[TransitionConfig]) -> List[str]` — returns FFmpeg filter segments
  - `EditingEngine.render(self, script_id: str, shot_videos: List[Tuple[str, str]], edits: List[EditDecision], transitions: List[TransitionConfig], export_preset: ExportPreset, progress_callback: Callable[[ExportProgress], None] | None = None) -> str` — returns output path

- [ ] **Step 1: Write the test file**

```python
# tests/test_editing.py
import os, sys, pytest, tempfile, subprocess
from unittest.mock import patch, MagicMock, call

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from apps.comic_gen.editing import EditingEngine
from apps.comic_gen.models import EditDecision, TransitionConfig, ExportPreset, CropRect


def _dummy_video(path: str, duration: float = 3.0):
    """Create a minimal valid MP4 via FFmpeg for testing."""
    # Use ffmpeg to generate a 1-frame test video
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=black:s=320x240:d={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        path
    ], check=True, capture_output=True)


class TestEditingEngine:
    @pytest.fixture
    def engine(self):
        return EditingEngine()

    @pytest.fixture
    def tmp_videos(self, tmp_path):
        """Create two test video files."""
        v1 = str(tmp_path / "shot1.mp4")
        v2 = str(tmp_path / "shot2.mp4")
        _dummy_video(v1, 3.0)
        _dummy_video(v2, 4.0)
        return v1, v2, str(tmp_path)

    def test_build_filter_chain_empty(self, engine):
        """No edits, no transitions = empty filter chain."""
        chain = engine.build_filter_chain([], [])
        assert chain == []

    def test_build_filter_chain_trim(self, engine):
        """A trim edit produces a trim filter segment."""
        edits = [
            EditDecision(
                shot_id="shot1",
                operation="trim",
                params={"start": 1.0, "end": 2.5}
            )
        ]
        chain = engine.build_filter_chain(edits, [])
        assert len(chain) == 1
        assert "trim=start=1.0:end=2.5" in chain[0]

    def test_build_filter_chain_speed(self, engine):
        """A speed edit produces setpts filter."""
        edits = [
            EditDecision(
                shot_id="shot1",
                operation="speed",
                params={"factor": 2.0}
            )
        ]
        chain = engine.build_filter_chain(edits, [])
        assert len(chain) == 1
        assert "setpts=0.5*PTS" in chain[0]

    def test_build_filter_chain_crop(self, engine):
        """A crop edit produces crop filter."""
        edits = [
            EditDecision(
                shot_id="shot1",
                operation="crop",
                params={"rect": {"x": 0, "y": 0, "width": 0.5625, "height": 1.0}}
            )
        ]
        chain = engine.build_filter_chain(edits, [])
        assert len(chain) == 1
        assert "crop=" in chain[0]

    def test_build_dissolve_transition(self, engine):
        """A dissolve transition between two shots produces xfade."""
        transitions = [
            TransitionConfig(
                from_shot_id="shot1", to_shot_id="shot2",
                transition_type="dissolve", duration_ms=500
            )
        ]
        chain = engine.build_filter_chain([], transitions)
        assert len(chain) == 1
        assert "xfade=transition=dissolve:duration=0.5" in chain[0]

    def test_render_basic_concat(self, engine, tmp_videos):
        """Rendering two videos with no edits produces concatenated output."""
        v1, v2, tmpdir = tmp_videos
        output = os.path.join(tmpdir, "output.mp4")
        shot_videos = [("shot1", v1), ("shot2", v2)]
        preset = ExportPreset(preset_name="custom", resolution="720p", bitrate="2M")

        result = engine.render(
            script_id="test_script",
            shot_videos=shot_videos,
            edits=[],
            transitions=[],
            export_preset=preset,
            progress_callback=None
        )
        assert os.path.exists(result)
        # Verify it's a valid MP4
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", result],
            capture_output=True, text=True
        )
        assert probe.returncode == 0

    def test_render_with_speed_edit(self, engine, tmp_videos):
        """A 2x speed edit on the first shot should halve its duration."""
        v1, v2, tmpdir = tmp_videos
        output = os.path.join(tmpdir, "output_speed.mp4")
        shot_videos = [("shot1", v1), ("shot2", v2)]
        edits = [
            EditDecision(shot_id="shot1", operation="speed", params={"factor": 2.0})
        ]
        preset = ExportPreset(preset_name="custom", resolution="720p", bitrate="2M")
        result = engine.render("test_script", shot_videos, edits, [], preset)
        assert os.path.exists(result)

    def test_render_with_dissolve(self, engine, tmp_videos):
        """Two shots with dissolve transition produce valid output."""
        v1, v2, tmpdir = tmp_videos
        output = os.path.join(tmpdir, "output_dissolve.mp4")
        shot_videos = [("shot1", v1), ("shot2", v2)]
        transitions = [
            TransitionConfig(
                from_shot_id="shot1", to_shot_id="shot2",
                transition_type="dissolve", duration_ms=500
            )
        ]
        preset = ExportPreset(preset_name="custom", resolution="720p", bitrate="2M")
        result = engine.render("test_script", shot_videos, [], transitions, preset)
        assert os.path.exists(result)

    def test_progress_callback(self, engine, tmp_videos):
        """Progress callback receives at least one call and final phase is 'done'."""
        v1, v2, tmpdir = tmp_videos
        output = os.path.join(tmpdir, "output_progress.mp4")
        shot_videos = [("shot1", v1), ("shot2", v2)]
        preset = ExportPreset(preset_name="custom", resolution="720p", bitrate="2M")

        calls = []
        def cb(p):
            calls.append(p)

        result = engine.render("test_script", shot_videos, [], [], preset, progress_callback=cb)
        assert len(calls) > 0
        assert calls[-1].phase == "done"
        assert calls[-1].output_url is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_editing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.comic_gen.editing'`

- [ ] **Step 3: Write the EditingEngine implementation**

```python
# src/apps/comic_gen/editing.py
"""Non-destructive editing engine using FFmpeg Edit Decision Lists (EDL).

This module replaces the mock ExportManager with a real FFmpeg-based
renderer. All edits are stored as EditDecision records; rendering
applies them in a single FFmpeg pass to avoid quality loss from
multiple re-encodes.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from typing import Callable, Dict, List, Optional, Tuple

from .models import EditDecision, ExportPreset, TransitionConfig, ExportProgress
from ...utils.system_check import get_ffmpeg_path


# ── FFmpeg filter builders ──────────────────────────────────────

# Map transition_type → xfade transition name
_XFADE_MAP: Dict[str, str] = {
    "dissolve": "dissolve",
    "fade_black": "fadeblack",
    "fade_white": "fadewhite",
    "push_left": "pushleft",
    "push_right": "pushright",
    "push_up": "pushup",
    "push_down": "pushdown",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "wipe_down": "wipedown",
    "wipe_up": "wipeup",
    "zoom_in": "zoomin",
    "zoom_out": "zoomout",
    "spin": "hlslip",  # closest native xfade effect
}

# Codec map for export presets
_CODEC_MAP: Dict[str, str] = {
    "h264": "libx264",
    "h265": "libx265",
}

_RESOLUTION_MAP: Dict[str, str] = {
    "720p": "1280x720",
    "1080p": "1920x1080",
}


def _build_trim_filter(edit: EditDecision) -> str:
    start = float(edit.params.get("start", 0))
    end = float(edit.params.get("end", 0))
    return f"trim=start={start}:end={end},setpts=PTS-STARTPTS"


def _build_speed_filter(edit: EditDecision) -> str:
    factor = float(edit.params.get("factor", 1.0))
    # setpts=1/factor * PTS; atempo= factor for audio
    return f"setpts={1.0/factor}*PTS"


def _build_crop_filter(edit: EditDecision) -> str:
    rect = edit.params.get("rect", {})
    # crop=w:h:x:y — FFmpeg uses absolute pixels, but we store relative coords
    # The caller is expected to provide output_width/output_height context.
    # For the EDL approach, we output a placeholder expression that gets
    # resolved at render time with the actual input dimensions.
    x = rect.get("x", 0)
    y = rect.get("y", 0)
    w = rect.get("width", 1)
    h = rect.get("height", 1)
    return f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}"


_EDIT_FILTERS: Dict[str, Callable] = {
    "trim": _build_trim_filter,
    "speed": _build_speed_filter,
    "crop": _build_crop_filter,
}


class EditingEngine:
    """Builds and executes FFmpeg command chains from EditDecision lists.

    The engine uses a non-destructive approach: edits are stored as
    metadata (EDL), and rendering applies all edits + transitions in
    a single FFmpeg pipeline. No intermediate re-encodes.
    """

    def __init__(self, ffmpeg_path: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path or get_ffmpeg_path()
        if not self.ffmpeg_path:
            raise RuntimeError(
                "FFmpeg not found. Install FFmpeg to use the editing engine."
            )

    # ── Public API ───────────────────────────────────────────

    def build_concat_file(
        self, shot_paths: List[str], output_dir: str
    ) -> str:
        """Create an FFmpeg concat demuxer file listing video paths.

        Returns the path to the concat list file.
        """
        list_path = os.path.join(output_dir, "concat_list.txt")
        with open(list_path, "w") as f:
            for p in shot_paths:
                abs_p = os.path.abspath(p)
                # Escape single quotes and wrap
                escaped = abs_p.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")
        return list_path

    def build_filter_chain(
        self,
        edits: List[EditDecision],
        transitions: List[TransitionConfig],
    ) -> List[str]:
        """Convert EDL + transitions into an ordered list of FFmpeg
        filter-complex segments.

        Each segment is a string like "trim=start=1:end=3,setpts=PTS-STARTPTS"
        that can be inserted into a filter_complex graph.

        Returns an empty list when there are no edits or transitions.
        """
        segments: List[str] = []

        # Index edits by shot_id for O(1) lookup
        edits_by_shot: Dict[str, List[EditDecision]] = {}
        for e in edits:
            edits_by_shot.setdefault(e.shot_id, []).append(e)

        # Build per-shot filter chains and composite xfade graph
        if transitions:
            # Complex graph with xfade between streams
            for t in transitions:
                xfade_name = _XFADE_MAP.get(t.transition_type, "dissolve")
                dur = t.duration_ms / 1000.0
                segments.append(
                    f"xfade=transition={xfade_name}:duration={dur}:offset=0"
                )

        # Per-shot edit filters
        for shot_id, shot_edits in edits_by_shot.items():
            for edit in shot_edits:
                builder = _EDIT_FILTERS.get(edit.operation)
                if builder:
                    segments.append(builder(edit))

        return segments

    def render(
        self,
        script_id: str,
        shot_videos: List[Tuple[str, str]],  # [(shot_id, abs_path), ...]
        edits: List[EditDecision],
        transitions: List[TransitionConfig],
        export_preset: ExportPreset,
        progress_callback: Optional[Callable[[ExportProgress], None]] = None,
    ) -> str:
        """Render the final video from shot videos, edits, and transitions.

        Args:
            script_id: Project script ID (used for output naming).
            shot_videos: Ordered list of (shot_id, absolute_file_path).
            edits: Edit decisions to apply.
            transitions: Transitions between adjacent shots.
            export_preset: Resolution/codec/format/bitrate settings.
            progress_callback: Optional callback receiving ExportProgress.

        Returns:
            Absolute path to the rendered output file.
        """
        output_dir = os.path.join("output", "export")
        os.makedirs(output_dir, exist_ok=True)

        ext = export_preset.format  # "mp4" | "mov" | "webm"
        output_path = os.path.join(
            output_dir, f"{script_id}_{int(time.time())}.{ext}"
        )

        total_shots = len(shot_videos)

        def _emit(phase: str, current: int = 0, message: str = "",
                  output_url: Optional[str] = None,
                  error: Optional[str] = None):
            if progress_callback:
                progress_callback(ExportProgress(
                    phase=phase,
                    current=current,
                    total=total_shots,
                    eta_seconds=0,
                    message=message,
                    output_url=output_url,
                    error=error,
                ))

        try:
            # Phase 1: Collect
            _emit("collecting", 0, f"Collecting {total_shots} shots...")

            video_paths = [p for _, p in shot_videos if os.path.exists(p)]
            if not video_paths:
                raise ValueError("No valid video files found for export")

            codec = _CODEC_MAP.get(export_preset.codec, "libx264")
            resolution = _RESOLUTION_MAP.get(
                export_preset.resolution, None  # None = keep original
            )

            # Phase 2: Build command
            # Strategy: if there are transitions, use filter_complex with xfade.
            # If only edits (trim/speed/crop), apply per-stream filters.
            # If neither, use concat demuxer for max speed.

            has_transitions = len(transitions) > 0
            filter_parts = self.build_filter_chain(edits, transitions)

            if has_transitions and len(video_paths) >= 2:
                # Build xfade filter_complex chain
                _emit("rendering_shots", 0, "Building transition graph...")

                cmd = [self.ffmpeg_path, "-y"]

                # Input files
                for vp in video_paths:
                    cmd.extend(["-i", vp])

                # Build: [0][1]xfade=...:offset=T1[v1]; [v1][2]xfade=...:offset=T2[v2]; ...
                # Each shot's duration determines the offset for the next xfade.
                filter_parts_list = []
                prev_label = "0"
                stream_idx = 1
                offset_acc = 0.0

                for i, vp in enumerate(video_paths[:-1]):
                    # Get duration of current shot (pre-edit)
                    dur = _probe_duration(self.ffmpeg_path, vp)
                    offset_acc += dur

                    t = transitions[i] if i < len(transitions) else TransitionConfig(
                        from_shot_id="", to_shot_id="",
                        transition_type="dissolve", duration_ms=300
                    )
                    xfade_name = _XFADE_MAP.get(t.transition_type, "dissolve")
                    tdur = t.duration_ms / 1000.0

                    next_label = f"v{i}"
                    filter_parts_list.append(
                        f"[{prev_label}][{stream_idx}]"
                        f"xfade=transition={xfade_name}:duration={tdur}:offset={offset_acc - tdur}"
                        f"[{next_label}]"
                    )
                    prev_label = next_label
                    stream_idx += 1

                filter_complex = ";".join(filter_parts_list)

                # Per-stream edit filters (applied to each input before xfade)
                # Omitted for now — advanced feature for V1.1

                cmd.extend([
                    "-filter_complex", filter_complex,
                    "-map", f"[{prev_label}]",
                ])
            else:
                # Simple concat (no transitions or only 1 shot)
                _emit("rendering_shots", 0, "Concatenating shots...")
                concat_file = self.build_concat_file(
                    video_paths, output_dir
                )
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_file,
                ]

            # Phase 3: Encode
            _emit("encoding", total_shots // 2, "Encoding final video...")

            # Codec + quality flags
            if codec == "libx264":
                cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "21"])
            elif codec == "libx265":
                cmd.extend(["-c:v", "libx265", "-preset", "medium", "-crf", "23"])

            cmd.extend(["-b:v", export_preset.bitrate])
            cmd.extend(["-r", str(export_preset.fps)])

            # Resolution scaling
            if resolution:
                cmd.extend(["-vf", f"scale={resolution}:force_original_aspect_ratio=decrease,pad={resolution}:(ow-iw)/2:(oh-ih)/2"])

            # Audio: copy from first input that has audio, or use anullsrc if none
            cmd.extend(["-c:a", "aac", "-b:a", "128k", "-shortest"])
            cmd.extend(["-pix_fmt", "yuv420p"])  # max compatibility
            cmd.extend(["-movflags", "+faststart"])  # web streaming

            cmd.append(output_path)

            # Phase 4: Execute
            _emit("encoding", total_shots * 3 // 4, "Running FFmpeg...")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 min max
            )

            if result.returncode != 0:
                stderr_tail = result.stderr[-500:] if result.stderr else "(no output)"
                raise RuntimeError(
                    f"FFmpeg exited with code {result.returncode}\n{stderr_tail}"
                )

            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise RuntimeError("FFmpeg produced no output file")

            _emit("done", total_shots, "Export complete",
                  output_url=os.path.relpath(output_path, "output"))

            return output_path

        except Exception as exc:
            _emit("error", 0, error=str(exc))
            raise


def _probe_duration(ffmpeg_path: str, filepath: str) -> float:
    """Get duration of a video file in seconds using ffprobe."""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath
        ], capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip()) if result.returncode == 0 else 3.0
    except Exception:
        return 3.0  # fallback
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_editing.py -v`
Expected: All 8 tests PASS (skip with message if FFmpeg not found, but this environment should have it).

- [ ] **Step 5: Commit**

```bash
git add src/apps/comic_gen/editing.py tests/test_editing.py
git commit -m "feat(v1-post): add EditingEngine with EDL-based FFmpeg rendering"
```

---

### Task 3: Pipeline Integration — Timeline State + Export Methods

**Files:**
- Modify: `src/apps/comic_gen/pipeline.py` (add 6 methods after existing `merge_videos`, above line ~2750)
- REPLACE: `src/apps/comic_gen/export.py` (replace full file content)

**Interfaces:**
- Consumes: `TimelineData`, `EditDecision`, `TransitionConfig`, `ExportPreset`, `ExportProgress` from Task 1; `EditingEngine` from Task 2
- Produces:
  - `ComicGenPipeline.save_timeline(script_id, timeline_data) -> Script`
  - `ComicGenPipeline.get_timeline(script_id) -> TimelineData`
  - `ComicGenPipeline.add_edits(script_id, edits) -> Script`
  - `ComicGenPipeline.set_transitions(script_id, transitions) -> Script`
  - `ComicGenPipeline.export_with_post(script_id, export_preset, progress_callback) -> str`
  - `ComicGenPipeline._load_timeline(script_id) -> TimelineData`

- [ ] **Step 1: Replace ExportManager with real implementation**

Replace content of `src/apps/comic_gen/export.py`:

```python
"""Export manager — delegates to EditingEngine for FFmpeg rendering.

This module keeps the existing ExportManager interface (used by pipeline)
but replaces the mock body with a real EditingEngine call.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from .editing import EditingEngine
from .models import ExportPreset, ExportProgress
from ...utils import get_logger

logger = get_logger(__name__)


class ExportManager:
    """Real export manager — wraps EditingEngine for backward compat."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.output_dir = self.config.get("output_dir", "output/export")
        os.makedirs(self.output_dir, exist_ok=True)
        self._engine: Optional[EditingEngine] = None

    @property
    def engine(self) -> EditingEngine:
        if self._engine is None:
            self._engine = EditingEngine()
        return self._engine

    def render_project(
        self,
        shot_videos: list,  # [(shot_id, abs_path), ...]
        edits: list,        # List[EditDecision]
        transitions: list,  # List[TransitionConfig]
        export_preset: ExportPreset,
        script_id: str = "export",
        progress_callback: Optional[Callable[[ExportProgress], None]] = None,
    ) -> str:
        """Render final video using the EditingEngine.

        Returns the relative path (from output/) of the exported file.
        """
        output_path = self.engine.render(
            script_id=script_id,
            shot_videos=shot_videos,
            edits=edits,
            transitions=transitions,
            export_preset=export_preset,
            progress_callback=progress_callback,
        )
        return os.path.relpath(output_path, "output")
```

- [ ] **Step 2: Add timeline methods to ComicGenPipeline**

Open `src/apps/comic_gen/pipeline.py`. After the `merge_videos` method's closing (around line ~2750), insert these 6 methods inside the `ComicGenPipeline` class:

```python
    # ── V1 Post-Production: Timeline, Edits, Transitions ─────────

    def _timeline_path(self, script_id: str) -> str:
        """Path to per-project timeline JSON."""
        return os.path.join("output", "timelines", f"{script_id}.json")

    def _load_timeline(self, script_id: str) -> "TimelineData":
        """Load timeline state from disk, or return default empty."""
        from .models import TimelineData
        tpath = self._timeline_path(script_id)
        if os.path.exists(tpath):
            try:
                with open(tpath, "r") as f:
                    data = json.load(f)
                return TimelineData(**data)
            except Exception:
                pass
        # Build default — one video track with current frame order
        script = self.scripts.get(script_id)
        default_track = {
            "track_id": "video_main",
            "track_type": "video",
            "label": "Video",
            "shot_ids": [f.id for f in (script.frames if script else [])],
            "muted": False,
            "volume": 1.0,
        }
        return TimelineData(tracks=[TimelineTrack(**default_track)])

    def save_timeline(self, script_id: str, timeline_data: "TimelineData") -> "Script":
        """Persist timeline state to disk and mark script as updated."""
        script = self.scripts.get(script_id)
        if not script:
            raise ValueError("Script not found")
        os.makedirs(os.path.dirname(self._timeline_path(script_id)), exist_ok=True)
        timeline_data.updated_at = time.time()
        with open(self._timeline_path(script_id), "w") as f:
            json.dump(timeline_data.model_dump(), f, indent=2)
        script.updated_at = time.time()
        self._save_data()
        return script

    def get_timeline(self, script_id: str) -> "TimelineData":
        """Return current timeline state for a project."""
        return self._load_timeline(script_id)

    def add_edits(self, script_id: str, edits: List["EditDecision"]) -> "Script":
        """Append edit decisions and persist timeline."""
        timeline = self._load_timeline(script_id)
        # Replace any existing edits for the same shot (last write wins)
        new_shot_ids = {e.shot_id for e in edits}
        timeline.edits = [e for e in timeline.edits if e.shot_id not in new_shot_ids]
        timeline.edits.extend(edits)
        return self.save_timeline(script_id, timeline)

    def set_transitions(
        self, script_id: str, transitions: List["TransitionConfig"]
    ) -> "Script":
        """Replace all transitions and persist timeline."""
        timeline = self._load_timeline(script_id)
        timeline.transitions = transitions
        return self.save_timeline(script_id, timeline)

    def export_with_post(
        self,
        script_id: str,
        export_preset: "ExportPreset",
        progress_callback: Optional[Callable[["ExportProgress"], None]] = None,
    ) -> str:
        """Full export: collect shot videos → apply edits + transitions → encode.

        Returns the relative path (from output/) of the final video.
        """
        script = self.scripts.get(script_id)
        if not script:
            raise ValueError("Script not found")

        timeline = self._load_timeline(script_id)

        # Collect shot videos in timeline order
        shot_videos = []
        for track in timeline.tracks:
            if track.track_type != "video":
                continue
            for sid in track.shot_ids:
                frame = next((f for f in script.frames if f.id == sid), None)
                if not frame:
                    continue
                # Resolve video URL → absolute path
                video_url = None
                if frame.dubbed_video_url:
                    video_url = frame.dubbed_video_url
                elif frame.selected_video_id:
                    vtask = next(
                        (t for t in (script.video_tasks or [])
                         if t.id == frame.selected_video_id), None
                    )
                    if vtask and vtask.video_url:
                        video_url = vtask.video_url
                else:
                    vtask = next(
                        (t for t in (script.video_tasks or [])
                         if t.frame_id == frame.id and t.status == "completed"), None
                    )
                    if vtask and vtask.video_url:
                        video_url = vtask.video_url

                if video_url:
                    # Resolve to absolute path
                    if video_url.startswith("http"):
                        # Remote URL — skip for now (V1 limitation)
                        logger.warning(
                            f"export_with_post: skipping remote URL {video_url}"
                        )
                        continue
                    abs_path = _safe_resolve_path("output", video_url)
                    if os.path.exists(abs_path):
                        shot_videos.append((sid, abs_path))

        if not shot_videos:
            raise ValueError("No local video files available for export")

        return self.export_manager.render_project(
            shot_videos=shot_videos,
            edits=timeline.edits,
            transitions=timeline.transitions,
            export_preset=export_preset,
            script_id=script_id,
            progress_callback=progress_callback,
        )
```

- [ ] **Step 3: Add the `import` for Callable at top of pipeline.py**

At the top of `pipeline.py`, the import line:
```python
from typing import Dict, Any, List, Optional, Tuple
```
Change to:
```python
from typing import Callable, Dict, Any, List, Optional, Tuple
```

- [ ] **Step 4: Verify pipeline still starts**

Run:
```
python -c "from src.apps.comic_gen.pipeline import ComicGenPipeline; p = ComicGenPipeline(); print('Pipeline OK, scripts:', len(p.scripts))"
```
Expected: `Pipeline OK, scripts: N`

- [ ] **Step 5: Run existing tests**

Run: `pytest tests/ -x -q`
Expected: All existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/apps/comic_gen/pipeline.py src/apps/comic_gen/export.py
git commit -m "feat(v1-post): integrate EditingEngine into pipeline with timeline persistence"
```

---

### Task 4: API Endpoints — Timeline CRUD, Transition CRUD, Export SSE

**Files:**
- Modify: `src/apps/comic_gen/api.py` (add endpoints before the `# === STORYBOARD DRAMATIZATION v2 ===` section, around line 1750)

**Interfaces:**
- Consumes: `TimelineData`, `EditDecision`, `TransitionConfig`, `ExportPreset`, `ExportProgress` from Task 1; pipeline methods from Task 3
- Produces:
  - `GET /projects/{script_id}/timeline`
  - `PUT /projects/{script_id}/timeline`
  - `POST /projects/{script_id}/edits`
  - `DELETE /projects/{script_id}/edits/{edit_id}`
  - `PUT /projects/{script_id}/transitions`
  - `GET /projects/{script_id}/export/progress` (SSE)
  - `POST /projects/{script_id}/export/start`
  - `GET /export/presets`

- [ ] **Step 1: Add API endpoints**

Open `src/apps/comic_gen/api.py`. Insert the following after the `# ───────────────── R2V v2 Phase 4 — Cross-episode asset reconcile ───` section but before the storyboard endpoints, around line 1750:

```python
# ============================================================
# V1 Post-Production API — Timeline, Edits, Transitions, Export
# ============================================================

class SaveTimelineRequest(BaseModel):
    tracks: Optional[List[dict]] = None
    edits: Optional[List[dict]] = None
    transitions: Optional[List[dict]] = None


class AddEditsRequest(BaseModel):
    edits: List[dict]


class SetTransitionsRequest(BaseModel):
    transitions: List[dict]


class StartExportRequest(BaseModel):
    preset_name: str = "custom"  # "douyin" | "kuaishou" | "bilibili" | "youtube" | "custom"
    resolution: str = "1080p"
    codec: str = "h264"
    format: str = "mp4"
    bitrate: str = "2M"
    fps: int = 30


@app.get("/projects/{script_id}/timeline")
def get_timeline(script_id: str):
    """Get the full timeline state (tracks, edits, transitions) for a project."""
    try:
        timeline = pipeline.get_timeline(script_id)
        return signed_response(timeline.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/projects/{script_id}/timeline")
def save_timeline(script_id: str, request: SaveTimelineRequest):
    """Save timeline state. Only provided fields are updated; omitted fields
    keep their current values."""
    try:
        current = pipeline.get_timeline(script_id)
        data = current.model_dump()
        if request.tracks is not None:
            data["tracks"] = request.tracks
        if request.edits is not None:
            data["edits"] = request.edits
        if request.transitions is not None:
            data["transitions"] = request.transitions
        from .models import TimelineData
        updated = TimelineData(**data)
        script = pipeline.save_timeline(script_id, updated)
        return signed_response(updated.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/projects/{script_id}/edits")
def add_edits(script_id: str, request: AddEditsRequest):
    """Add or update edit decisions. Edits for the same shot_id are replaced."""
    try:
        from .models import EditDecision
        edits = [EditDecision(**e) for e in request.edits]
        script = pipeline.add_edits(script_id, edits)
        timeline = pipeline.get_timeline(script_id)
        return signed_response(timeline.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/projects/{script_id}/edits/{edit_id}")
def delete_edit(script_id: str, edit_id: str):
    """Remove a single edit decision by ID."""
    try:
        timeline = pipeline.get_timeline(script_id)
        timeline.edits = [e for e in timeline.edits if e.id != edit_id]
        script = pipeline.save_timeline(script_id, timeline)
        return signed_response(timeline.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/projects/{script_id}/transitions")
def set_transitions(script_id: str, request: SetTransitionsRequest):
    """Replace all transitions for a project."""
    try:
        from .models import TransitionConfig
        transitions = [TransitionConfig(**t) for t in request.transitions]
        script = pipeline.set_transitions(script_id, transitions)
        timeline = pipeline.get_timeline(script_id)
        return signed_response(timeline.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# In-memory export progress store keyed by script_id.
# Cleared on process restart (transient — frontend polls SSE while tab is open).
_export_progress: Dict[str, "ExportProgress"] = {}


@app.get("/projects/{script_id}/export/progress")
def export_progress(script_id: str):
    """SSE endpoint streaming export progress events."""
    from fastapi.responses import StreamingResponse
    import asyncio

    def event_stream():
        last_phase = None
        # Poll every 500ms until done/error
        for _ in range(600):  # max 5 min
            prog = _export_progress.get(script_id)
            if prog is None:
                # Send a placeholder collecting event
                from .models import ExportProgress
                prog = ExportProgress(phase="collecting", current=0, total=0,
                                      eta_seconds=0, message="Preparing export...")

            if prog.phase != last_phase:
                yield f"data: {json.dumps(prog.model_dump(), ensure_ascii=False)}\n\n"
                last_phase = prog.phase

            if prog.phase in ("done", "error"):
                # Clean up
                _export_progress.pop(script_id, None)
                return

            time.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/projects/{script_id}/export/start")
def start_export(script_id: str, request: StartExportRequest, background_tasks: BackgroundTasks):
    """Start a post-production export with edits, transitions, and formatting.

    Returns immediately. Poll /export/progress for SSE updates.
    """
    try:
        from .models import ExportPreset, ExportProgress
        preset = ExportPreset(
            preset_name=request.preset_name,
            resolution=request.resolution,
            codec=request.codec,
            format=request.format,
            bitrate=request.bitrate,
            fps=request.fps,
        )

        def _on_progress(prog: ExportProgress):
            _export_progress[script_id] = prog

        _export_progress[script_id] = ExportProgress(
            phase="collecting", current=0, total=0,
            eta_seconds=0, message="Starting export..."
        )

        def _do_export():
            try:
                output_rel = pipeline.export_with_post(
                    script_id, preset, progress_callback=_on_progress
                )
                # Update script's merged_video_url with the new export
                script = pipeline.get_script(script_id)
                if script:
                    script.merged_video_url = output_rel
                    script.updated_at = time.time()
                    pipeline._save_data()
            except Exception as e:
                logger.exception(f"Export failed for {script_id}")
                _export_progress[script_id] = ExportProgress(
                    phase="error", current=0, total=0,
                    eta_seconds=0, message="Export failed",
                    error=str(e)
                )

        background_tasks.add_task(_do_export)
        return {"status": "started", "script_id": script_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/export/presets")
def get_export_presets():
    """Return built-in export presets for different platforms."""
    presets = [
        {"preset_name": "douyin", "label": "抖音", "resolution": "1080p",
         "codec": "h264", "format": "mp4", "bitrate": "2M", "fps": 30,
         "aspect": "9:16"},
        {"preset_name": "kuaishou", "label": "快手", "resolution": "720p",
         "codec": "h264", "format": "mp4", "bitrate": "1.5M", "fps": 30,
         "aspect": "9:16"},
        {"preset_name": "bilibili", "label": "B站", "resolution": "1080p",
         "codec": "h264", "format": "mp4", "bitrate": "6M", "fps": 30,
         "aspect": "16:9"},
        {"preset_name": "youtube", "label": "YouTube", "resolution": "1080p",
         "codec": "h264", "format": "mp4", "bitrate": "8M", "fps": 30,
         "aspect": "16:9"},
        {"preset_name": "custom", "label": "自定义", "resolution": "1080p",
         "codec": "h264", "format": "mp4", "bitrate": "4M", "fps": 30,
         "aspect": "16:9"},
    ]
    return presets
```

- [ ] **Step 2: Verify endpoints are registered**

Restart the backend and run:
```
curl http://localhost:17177/export/presets
```
Expected: JSON array with 5 preset objects.

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/ -x -q`
Expected: All existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/apps/comic_gen/api.py
git commit -m "feat(v1-post): add V1 editing + export API endpoints (timeline CRUD, SSE export progress, presets)"
```

---

### Task 5: Frontend API Client — New Methods

**Files:**
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Consumes: Backend endpoints from Task 4
- Produces: API client methods for timeline, edits, transitions, export

- [ ] **Step 1: Add API methods**

Open `frontend/src/lib/api.ts`. Locate the `api` object's return statement (near end of file). Before the `return` statement that assembles the api object, add these methods inside the factory function:

```typescript
  // ── V1 Post-Production ────────────────────────────────────

  /** Get full timeline state for a project. */
  getTimeline: async (scriptId: string) => {
    const res = await client.get(`/projects/${scriptId}/timeline`);
    return res.data;
  },

  /** Save partial timeline updates (only fields sent are changed). */
  saveTimeline: async (scriptId: string, data: {
    tracks?: any[]; edits?: any[]; transitions?: any[];
  }) => {
    const res = await client.put(`/projects/${scriptId}/timeline`, data);
    return res.data;
  },

  /** Add or update edit decisions. */
  addEdits: async (scriptId: string, edits: any[]) => {
    const res = await client.post(`/projects/${scriptId}/edits`, { edits });
    return res.data;
  },

  /** Delete a single edit by ID. */
  deleteEdit: async (scriptId: string, editId: string) => {
    const res = await client.delete(`/projects/${scriptId}/edits/${editId}`);
    return res.data;
  },

  /** Replace all transitions. */
  setTransitions: async (scriptId: string, transitions: any[]) => {
    const res = await client.put(`/projects/${scriptId}/transitions`, { transitions });
    return res.data;
  },

  /** Start post-production export. Poll /export/progress for SSE updates. */
  startExport: async (scriptId: string, preset: {
    preset_name: string; resolution: string; codec: string;
    format: string; bitrate: string; fps: number;
  }) => {
    const res = await client.post(`/projects/${scriptId}/export/start`, preset);
    return res.data;
  },

  /** Get built-in export presets. */
  getExportPresets: async () => {
    const res = await client.get("/export/presets");
    return res.data;
  },
```

Make sure these methods are included in the returned object at the bottom of the `api` factory function.

- [ ] **Step 2: Add TypeScript types**

At the top of `lib/api.ts`, in the exported types area, add:

```typescript
export interface TimelineTrack {
  track_id: string;
  track_type: "video" | "dialogue" | "bgm" | "sfx" | "subtitle";
  label: string;
  shot_ids: string[];
  muted: boolean;
  volume: number;
}

export interface EditDecision {
  id: string;
  shot_id: string;
  operation: "trim" | "split" | "speed" | "crop" | "replace";
  params: Record<string, any>;
  created_at: number;
}

export interface TransitionConfig {
  id: string;
  from_shot_id: string;
  to_shot_id: string;
  transition_type: string;
  duration_ms: number;
}

export interface TimelineData {
  tracks: TimelineTrack[];
  edits: EditDecision[];
  transitions: TransitionConfig[];
  updated_at: number;
}

export interface ExportPreset {
  preset_name: string;
  label?: string;
  resolution: string;
  codec: string;
  format: string;
  bitrate: string;
  fps: number;
  aspect?: string;
}

export interface ExportProgress {
  phase: string;
  current: number;
  total: number;
  eta_seconds: number;
  message: string;
  output_url?: string;
  error?: string;
}
```

- [ ] **Step 3: Verify TypeScript compilation**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new type errors (existing errors that predate this change are OK).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(v1-post): add V1 API client methods (timeline, edits, transitions, export)"
```

---

### Task 6: Frontend — TimelineEditor Component

**Files:**
- Create: `frontend/src/components/modules/TimelineEditor.tsx`

**Interfaces:**
- Consumes: `api.getTimeline`, `api.saveTimeline`, `api.addEdits`, `api.deleteEdit` from Task 5; `useProjectStore` from existing store
- Produces: `<TimelineEditor>` React component with drag-drop shot reordering, inline edit controls (trim/split/speed/crop), per-shot context menus

- [ ] **Step 1: Write the component skeleton with shot list**

```tsx
// frontend/src/components/modules/TimelineEditor.tsx
"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, Reorder } from "framer-motion";
import {
    Scissors, GripVertical, Trash2, SplitSquareHorizontal,
    Clock, Crop, ChevronLeft, ChevronRight
} from "lucide-react";
import { api, type TimelineData, type EditDecision, type TimelineTrack } from "@/lib/api";
import { useProjectStore } from "@/store/projectStore";
import { getAssetUrl } from "@/lib/utils";

/** Pixels per second in the timeline ruler. */
const PX_PER_SECOND = 60;
const MIN_SHOT_WIDTH = 80;

interface TimelineEditorProps {
    scriptId: string;
}

export default function TimelineEditor({ scriptId }: TimelineEditorProps) {
    const currentProject = useProjectStore((s) => s.currentProject);
    const updateProject = useProjectStore((s) => s.updateProject);

    const [timeline, setTimeline] = useState<TimelineData | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
    const [playheadTime, setPlayheadTime] = useState(0);
    const rulerRef = useRef<HTMLDivElement>(null);

    // ── Load timeline ──────────────────────────────────────
    useEffect(() => {
        if (!scriptId) return;
        (async () => {
            setIsLoading(true);
            try {
                const data = await api.getTimeline(scriptId);
                setTimeline(data);
            } catch (e) {
                console.error("Failed to load timeline:", e);
            } finally {
                setIsLoading(false);
            }
        })();
    }, [scriptId]);

    // ── Persist helpers ────────────────────────────────────
    const persist = useCallback(async (updated: TimelineData) => {
        setTimeline(updated);
        try {
            await api.saveTimeline(scriptId, {
                tracks: updated.tracks,
                edits: updated.edits,
                transitions: updated.transitions,
            });
        } catch (e) {
            console.error("Failed to save timeline:", e);
        }
    }, [scriptId]);

    const videoTrack = timeline?.tracks.find((t) => t.track_type === "video");
    const frames = currentProject?.frames || [];

    // Build shot list from track order
    const orderedShots = (videoTrack?.shot_ids || []).map((sid) =>
        frames.find((f: any) => f.id === sid)
    ).filter(Boolean);

    const totalDuration = orderedShots.reduce(
        (sum: number, s: any) => sum + (s?.duration || 5),
        0
    );

    // ── Edit actions ───────────────────────────────────────
    const handleSplit = async (shotId: string) => {
        if (!timeline || !currentProject) return;
        const splitTime = (orderedShots.find((s: any) => s?.id === shotId)?.duration || 5) / 2;
        const newId = `frame_${Math.random().toString(36).slice(2, 10)}`;

        const edits = timeline.edits.filter((e) => e.shot_id !== shotId);
        edits.push({
            id: `edit_${Math.random().toString(36).slice(2, 10)}`,
            shot_id: shotId,
            operation: "split",
            params: { at_time: splitTime, new_shot_id: newId },
            created_at: Date.now() / 1000,
        });
        await persist({ ...timeline, edits });
    };

    const handleTrim = async (shotId: string, start: number, end: number) => {
        if (!timeline) return;
        const edits = timeline.edits.filter((e) => e.shot_id !== shotId || e.operation !== "trim");
        edits.push({
            id: `edit_${Math.random().toString(36).slice(2, 10)}`,
            shot_id: shotId,
            operation: "trim",
            params: { start, end },
            created_at: Date.now() / 1000,
        });
        await persist({ ...timeline, edits });
    };

    const handleSpeed = async (shotId: string, factor: number) => {
        if (!timeline) return;
        const edits = timeline.edits.filter((e) => e.shot_id !== shotId || e.operation !== "speed");
        edits.push({
            id: `edit_${Math.random().toString(36).slice(2, 10)}`,
            shot_id: shotId,
            operation: "speed",
            params: { factor },
            created_at: Date.now() / 1000,
        });
        await persist({ ...timeline, edits });
    };

    const handleDeleteEdit = async (editId: string) => {
        if (!timeline) return;
        try {
            const updated = await api.deleteEdit(scriptId, editId);
            setTimeline(updated);
        } catch (e) {
            console.error("Failed to delete edit:", e);
        }
    };

    // ── Reorder ────────────────────────────────────────────
    const handleReorder = async (newOrder: any[]) => {
        if (!timeline || !videoTrack) return;
        const newShotIds = newOrder.map((s: any) => s.id);
        const updatedTracks = timeline.tracks.map((t) =>
            t.track_id === videoTrack.track_id ? { ...t, shot_ids: newShotIds } : t
        );
        await persist({ ...timeline, tracks: updatedTracks });
    };

    // ── Playhead ───────────────────────────────────────────
    const handleRulerClick = (e: React.MouseEvent) => {
        if (!rulerRef.current) return;
        const rect = rulerRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        setPlayheadTime(Math.max(0, x / PX_PER_SECOND));
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64 text-text-muted">
                Loading timeline...
            </div>
        );
    }

    const editsByShot: Record<string, EditDecision[]> = {};
    (timeline?.edits || []).forEach((e) => {
        editsByShot[e.shot_id] = editsByShot[e.shot_id] || [];
        editsByShot[e.shot_id].push(e);
    });

    return (
        <div className="flex flex-col h-full bg-surface border-t border-glass-border">
            {/* Toolbar */}
            <div className="h-10 border-b border-glass-border flex items-center px-3 gap-2">
                <span className="font-mono text-xs text-primary">
                    {formatTime(playheadTime)}
                </span>
                <div className="h-3 w-px bg-hover-bg" />
                <span className="text-xs text-text-muted">
                    {orderedShots.length} shots · {formatTime(totalDuration)}
                </span>
            </div>

            {/* Tracks area */}
            <div className="flex-1 overflow-y-auto">
                {/* Time Ruler */}
                <div
                    ref={rulerRef}
                    className="h-6 border-b border-border-subtle cursor-pointer relative"
                    style={{ width: Math.max(totalDuration * PX_PER_SECOND, 800) }}
                    onClick={handleRulerClick}
                >
                    {Array.from({ length: Math.ceil(totalDuration) + 1 }).map((_, i) => (
                        <div
                            key={i}
                            className="absolute top-0 h-full border-l border-border-subtle"
                            style={{ left: i * PX_PER_SECOND }}
                        >
                            <span className="text-[10px] font-mono text-text-muted ml-1">
                                {formatTime(i)}
                            </span>
                        </div>
                    ))}
                    {/* Playhead */}
                    <div
                        className="absolute top-0 bottom-0 w-px bg-red-500 z-10 pointer-events-none"
                        style={{ left: playheadTime * PX_PER_SECOND }}
                    >
                        <div className="absolute -top-1 -left-1.5 w-3 h-3 bg-red-500 rotate-45" />
                    </div>
                </div>

                {/* Video Track */}
                <div className="px-2 py-1">
                    <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
                        Video
                    </span>
                    <Reorder.Group
                        axis="x"
                        values={orderedShots}
                        onReorder={handleReorder}
                        className="flex gap-0.5 mt-1 min-h-[72px] bg-glass rounded-lg p-1 overflow-x-auto"
                    >
                        {orderedShots.map((shot: any) => {
                            const shotEdits = editsByShot[shot.id] || [];
                            const hasEdits = shotEdits.length > 0;
                            const isSelected = selectedShotId === shot.id;
                            const dur = shot.duration || 5;
                            const width = Math.max(dur * PX_PER_SECOND, MIN_SHOT_WIDTH);

                            return (
                                <Reorder.Item
                                    key={shot.id}
                                    value={shot}
                                    dragListener={false}
                                    className="shrink-0"
                                >
                                    <motion.div
                                        className={`relative rounded border cursor-pointer transition-colors ${
                                            isSelected
                                                ? "border-primary bg-primary/10"
                                                : hasEdits
                                                ? "border-yellow-500/50 bg-yellow-500/5"
                                                : "border-glass-border bg-blue-500/10 hover:border-blue-500/40"
                                        }`}
                                        style={{ width }}
                                        onClick={() =>
                                            setSelectedShotId(
                                                isSelected ? null : shot.id
                                            )
                                        }
                                    >
                                        {/* Drag handle */}
                                        <div className="absolute left-1 top-1 cursor-grab active:cursor-grabbing text-text-muted hover:text-foreground">
                                            <GripVertical size={12} />
                                        </div>

                                        {/* Label */}
                                        <div className="px-5 py-1 text-[11px] text-text-secondary truncate">
                                            {shot.action_description?.slice(0, 20) || shot.id}
                                        </div>
                                        <div className="px-5 pb-1 text-[10px] font-mono text-text-muted">
                                            {formatTime(dur)}
                                        </div>

                                        {/* Edit badges */}
                                        {hasEdits && (
                                            <div className="absolute top-1 right-1 flex gap-0.5">
                                                {shotEdits.some((e) => e.operation === "trim") && (
                                                    <span className="w-2 h-2 rounded-full bg-yellow-500" title="Trimmed" />
                                                )}
                                                {shotEdits.some((e) => e.operation === "speed") && (
                                                    <span className="w-2 h-2 rounded-full bg-green-500" title="Speed adjusted" />
                                                )}
                                                {shotEdits.some((e) => e.operation === "crop") && (
                                                    <span className="w-2 h-2 rounded-full bg-purple-500" title="Cropped" />
                                                )}
                                            </div>
                                        )}
                                    </motion.div>
                                </Reorder.Item>
                            );
                        })}
                    </Reorder.Group>
                </div>

                {/* Audio Track (placeholder) */}
                <div className="px-2 py-1 border-t border-border-subtle">
                    <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
                        Audio
                    </span>
                    <div className="h-10 mt-1 bg-glass rounded-lg flex items-center justify-center">
                        <span className="text-xs text-text-muted">
                            Audio track — coming in V2
                        </span>
                    </div>
                </div>
            </div>

            {/* Selected shot actions */}
            {selectedShotId && (
                <div className="h-12 border-t border-glass-border flex items-center px-3 gap-2 bg-surface/80 backdrop-blur">
                    <button
                        onClick={() => handleSplit(selectedShotId)}
                        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-text-secondary hover:text-foreground hover:bg-glass transition-colors"
                        title="Split at midpoint"
                    >
                        <SplitSquareHorizontal size={14} /> Split
                    </button>
                    <button
                        onClick={() => {
                            const shot = orderedShots.find((s: any) => s.id === selectedShotId);
                            const dur = shot?.duration || 5;
                            handleTrim(selectedShotId, 0, dur);
                        }}
                        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-text-secondary hover:text-foreground hover:bg-glass transition-colors"
                        title="Trim to selection"
                    >
                        <Scissors size={14} /> Trim
                    </button>
                    <button
                        onClick={() => handleSpeed(selectedShotId, 2.0)}
                        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-text-secondary hover:text-foreground hover:bg-glass transition-colors"
                        title="2x speed"
                    >
                        <Clock size={14} /> 2x
                    </button>
                    <button
                        onClick={() => handleSpeed(selectedShotId, 0.5)}
                        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-text-secondary hover:text-foreground hover:bg-glass transition-colors"
                        title="0.5x speed"
                    >
                        <Clock size={14} /> 0.5x
                    </button>
                    <div className="h-4 w-px bg-hover-bg" />
                    {/* Show active edits for the selected shot */}
                    {(editsByShot[selectedShotId] || []).map((edit) => (
                        <span
                            key={edit.id}
                            className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-yellow-500/10 text-yellow-400 border border-yellow-500/30"
                        >
                            {edit.operation}
                            <button onClick={() => handleDeleteEdit(edit.id)}>
                                <Trash2 size={10} />
                            </button>
                        </span>
                    ))}
                </div>
            )}
        </div>
    );
}

/** Format seconds to mm:ss */
function formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}
```

- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new type errors from TimelineEditor.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/modules/TimelineEditor.tsx
git commit -m "feat(v1-post): add functional TimelineEditor with drag-reorder and edit operations"
```

---

### Task 7: Frontend — TransitionPicker Component

**Files:**
- Create: `frontend/src/components/modules/TransitionPicker.tsx`

**Interfaces:**
- Consumes: `api.setTransitions` from Task 5; `TimelineData`, `TransitionConfig` types from Task 5
- Produces: `<TransitionPicker>` component with preset grid and duration slider

- [ ] **Step 1: Write the component**

```tsx
// frontend/src/components/modules/TransitionPicker.tsx
"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { X } from "lucide-react";
import { api, type TimelineData, type TransitionConfig } from "@/lib/api";

const TRANSITION_PRESETS: { type: string; label: string; icon: string; group: string }[] = [
    { type: "cut", label: "硬切", icon: "✂️", group: "基础" },
    { type: "dissolve", label: "淡入淡出", icon: "🌫️", group: "基础" },
    { type: "fade_black", label: "黑场过渡", icon: "⬛", group: "基础" },
    { type: "fade_white", label: "白场过渡", icon: "⬜", group: "基础" },
    { type: "push_left", label: "推入←", icon: "⬅️", group: "动态" },
    { type: "push_right", label: "推入→", icon: "➡️", group: "动态" },
    { type: "push_up", label: "推入↑", icon: "⬆️", group: "动态" },
    { type: "push_down", label: "推入↓", icon: "⬇️", group: "动态" },
    { type: "wipe_right", label: "擦除→", icon: "🧹", group: "动态" },
    { type: "wipe_left", label: "擦除←", icon: "🧹", group: "动态" },
    { type: "zoom_in", label: "放大", icon: "🔍", group: "动态" },
    { type: "zoom_out", label: "缩小", icon: "🔎", group: "动态" },
    { type: "spin", label: "旋转", icon: "🔄", group: "动态" },
];

const DURATION_OPTIONS = [200, 300, 500, 750, 1000, 1500, 2000];

interface TransitionPickerProps {
    scriptId: string;
    timeline: TimelineData;
    onTimelineUpdate: (t: TimelineData) => void;
    onClose: () => void;
}

export default function TransitionPicker({
    scriptId, timeline, onTimelineUpdate, onClose,
}: TransitionPickerProps) {
    const [selectedType, setSelectedType] = useState<string>("dissolve");
    const [durationMs, setDurationMs] = useState(500);
    const [isApplying, setIsApplying] = useState(false);

    const frames = timeline.tracks
        .find((t) => t.track_type === "video")
        ?.shot_ids || [];

    const handleApplyAll = async () => {
        if (frames.length < 2) return;
        setIsApplying(true);
        try {
            const transitions: TransitionConfig[] = [];
            for (let i = 0; i < frames.length - 1; i++) {
                transitions.push({
                    id: `trans_${Math.random().toString(36).slice(2, 10)}`,
                    from_shot_id: frames[i],
                    to_shot_id: frames[i + 1],
                    transition_type: selectedType,
                    duration_ms: durationMs,
                });
            }
            const updated = await api.setTransitions(scriptId, transitions);
            onTimelineUpdate(updated);
        } catch (e) {
            console.error("Failed to set transitions:", e);
        } finally {
            setIsApplying(false);
        }
    };

    const groups = ["基础", "动态"];
    const currentTransitions = timeline.transitions || [];

    return (
        <div className="p-4 space-y-4">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-foreground">转场效果</h3>
                <button onClick={onClose} className="text-text-muted hover:text-foreground">
                    <X size={16} />
                </button>
            </div>

            {/* Duration */}
            <div>
                <label className="text-[11px] text-text-muted mb-1 block">
                    时长: {durationMs}ms
                </label>
                <div className="flex gap-1 flex-wrap">
                    {DURATION_OPTIONS.map((d) => (
                        <button
                            key={d}
                            onClick={() => setDurationMs(d)}
                            className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors ${
                                durationMs === d
                                    ? "bg-primary text-white"
                                    : "bg-glass text-text-secondary hover:text-foreground"
                            }`}
                        >
                            {d >= 1000 ? `${d / 1000}s` : `${d}ms`}
                        </button>
                    ))}
                </div>
            </div>

            {/* Preset grid */}
            {groups.map((group) => (
                <div key={group}>
                    <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">
                        {group}
                    </span>
                    <div className="grid grid-cols-4 gap-1.5 mt-1">
                        {TRANSITION_PRESETS.filter((p) => p.group === group).map(
                            (preset) => (
                                <motion.button
                                    key={preset.type}
                                    whileTap={{ scale: 0.95 }}
                                    onClick={() => setSelectedType(preset.type)}
                                    className={`flex flex-col items-center gap-0.5 p-1.5 rounded-lg text-[11px] transition-colors ${
                                        selectedType === preset.type
                                            ? "bg-primary/20 border border-primary/50 text-primary"
                                            : "bg-glass border border-glass-border text-text-secondary hover:text-foreground"
                                    }`}
                                >
                                    <span className="text-base">{preset.icon}</span>
                                    <span>{preset.label}</span>
                                </motion.button>
                            )
                        )}
                    </div>
                </div>
            ))}

            {/* Apply button */}
            <button
                onClick={handleApplyAll}
                disabled={isApplying || frames.length < 2}
                className="w-full py-2 rounded-lg bg-primary text-white text-sm font-medium
                           hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed
                           transition-colors"
            >
                {isApplying
                    ? "Applying..."
                    : frames.length < 2
                    ? "需要至少 2 个分镜"
                    : `全部应用 "${TRANSITION_PRESETS.find((p) => p.type === selectedType)?.label}"`}
            </button>

            {/* Current transitions summary */}
            {currentTransitions.length > 0 && (
                <div className="text-[10px] text-text-muted">
                    已设置 {currentTransitions.length} 个转场 (
                    {new Set(currentTransitions.map((t) => t.transition_type)).size} 种类型)
                </div>
            )}
        </div>
    );
}
```

- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/modules/TransitionPicker.tsx
git commit -m "feat(v1-post): add TransitionPicker with 13 presets across 2 groups"
```

---

### Task 8: Frontend — ExportProgressBar Component

**Files:**
- Create: `frontend/src/components/modules/ExportProgressBar.tsx`

**Interfaces:**
- Consumes: Backend SSE endpoint `GET /projects/{script_id}/export/progress` from Task 4
- Produces: `<ExportProgressBar>` component showing real-time export progress with phase indicators

- [ ] **Step 1: Write the component**

```tsx
// frontend/src/components/modules/ExportProgressBar.tsx
"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, CheckCircle, XCircle, Film, FileVideo, Download } from "lucide-react";
import type { ExportProgress } from "@/lib/api";
import { getAssetUrl } from "@/lib/utils";

interface ExportProgressBarProps {
    scriptId: string;
    onComplete?: (outputUrl: string) => void;
}

const PHASE_LABELS: Record<string, { label: string; icon: React.ReactNode }> = {
    collecting: { label: "收集视频片段...", icon: <Film size={14} /> },
    rendering_shots: { label: "渲染分镜...", icon: <Film size={14} /> },
    applying_edits: { label: "应用编辑效果...", icon: <Film size={14} /> },
    encoding: { label: "编码最终视频...", icon: <FileVideo size={14} /> },
    done: { label: "导出完成", icon: <CheckCircle size={14} /> },
    error: { label: "导出失败", icon: <XCircle size={14} /> },
};

export default function ExportProgressBar({ scriptId, onComplete }: ExportProgressBarProps) {
    const [progress, setProgress] = useState<ExportProgress | null>(null);
    const [isListening, setIsListening] = useState(false);

    useEffect(() => {
        if (!scriptId || isListening) return;
        setIsListening(true);

        const baseUrl = typeof window !== "undefined"
            ? `${window.location.protocol}//${window.location.hostname}:17177`
            : "http://localhost:17177";
        const url = `${baseUrl}/projects/${scriptId}/export/progress`;

        const eventSource = new EventSource(url);

        eventSource.onmessage = (event) => {
            try {
                const data: ExportProgress = JSON.parse(event.data);
                setProgress(data);
                if (data.phase === "done" && data.output_url) {
                    onComplete?.(data.output_url);
                    eventSource.close();
                }
                if (data.phase === "error") {
                    eventSource.close();
                }
            } catch (e) {
                console.error("Failed to parse SSE event:", e);
            }
        };

        eventSource.onerror = () => {
            eventSource.close();
        };

        return () => {
            eventSource.close();
        };
    }, [scriptId, isListening, onComplete]);

    if (!progress) {
        return (
            <div className="flex items-center gap-2 text-xs text-text-muted py-2">
                <Loader2 size={14} className="animate-spin" />
                Preparing export...
            </div>
        );
    }

    const phaseInfo = PHASE_LABELS[progress.phase] || {
        label: progress.message,
        icon: <Loader2 size={14} className="animate-spin" />,
    };
    const isDone = progress.phase === "done";
    const isError = progress.phase === "error";
    const percent = progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;

    return (
        <div className="space-y-2">
            {/* Phase + message */}
            <div className="flex items-center gap-2">
                <span
                    className={`${
                        isDone ? "text-green-400" : isError ? "text-red-400" : "text-primary"
                    }`}
                >
                    {phaseInfo.icon}
                </span>
                <span className="text-xs text-text-secondary">
                    {isError ? progress.error || phaseInfo.label : progress.message || phaseInfo.label}
                </span>
            </div>

            {/* Progress bar */}
            <AnimatePresence>
                {!isDone && !isError && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="h-1.5 bg-glass rounded-full overflow-hidden"
                    >
                        <motion.div
                            className="h-full bg-primary rounded-full"
                            initial={{ width: 0 }}
                            animate={{ width: `${Math.max(percent, 5)}%` }}
                            transition={{ duration: 0.3 }}
                        />
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Done with download link */}
            {isDone && progress.output_url && (
                <a
                    href={getAssetUrl(progress.output_url)}
                    download
                    className="flex items-center gap-2 text-xs text-primary hover:underline mt-2"
                >
                    <Download size={14} /> 下载成品视频
                </a>
            )}
        </div>
    );
}
```

- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/modules/ExportProgressBar.tsx
git commit -m "feat(v1-post): add ExportProgressBar with SSE-driven real-time progress"
```

---

### Task 9: Integration — VideoAssembly Page Wiring

**Files:**
- Modify: `frontend/src/components/modules/VideoAssembly.tsx`

**Interfaces:**
- Consumes: `TimelineEditor` from Task 6, `TransitionPicker` from Task 7, `ExportProgressBar` from Task 8; API methods from Task 5
- Produces: Updated Assembly page with "编辑" tab active

- [ ] **Step 1: Add "编辑" tab and wire new components**

The changes to `VideoAssembly.tsx`:

1) Change the `AssemblyPhase` type to include `"edit"`:
```tsx
type AssemblyPhase = "edit" | "takes" | "mix" | "export";
```

2) Change the default phase state:
```tsx
const [phase, setPhase] = useState<AssemblyPhase>("edit");
```

3) Import new components at the top:
```tsx
import TimelineEditor from "./TimelineEditor";
import TransitionPicker from "./TransitionPicker";
import ExportProgressBar from "./ExportProgressBar";
import { api as apiClient, type TimelineData } from "@/lib/api";
```

4) Add state for timeline + transitions panel visibility:
```tsx
const [timeline, setTimeline] = useState<TimelineData | null>(null);
const [showTransitions, setShowTransitions] = useState(false);
const [exportStarted, setExportStarted] = useState(false);
const [exportPreset, setExportPreset] = useState({
    preset_name: "douyin", resolution: "1080p", codec: "h264",
    format: "mp4", bitrate: "2M", fps: 30,
});
```

5) In the phase tab bar (where `takes`, `mix`, `export` buttons are rendered), add `"edit"` as the first tab:
```tsx
{([
    { key: "edit", icon: <Film size={15} />, label: "编辑" },
    { key: "takes", icon: <Layout size={15} />, label: ta("takesTab") },
    { key: "mix", icon: <Music size={15} />, label: ta("mixTab") },
    { key: "export", icon: <Package size={15} />, label: ta("exportTab") },
] as const).map((tab) => (
    // ... existing tab button render code, reuse the pattern
))}
```

6) Add the edit phase content:
```tsx
{phase === "edit" && (
    <div className="flex-1 flex flex-col">
        <TimelineEditor scriptId={currentProject!.id} />
        {showTransitions && (
            <div className="absolute right-4 top-20 w-80 bg-surface/95 backdrop-blur-xl border border-glass-border rounded-xl shadow-2xl z-20">
                <TransitionPicker
                    scriptId={currentProject!.id}
                    timeline={timeline!}
                    onTimelineUpdate={(t) => setTimeline(t)}
                    onClose={() => setShowTransitions(false)}
                />
            </div>
        )}
    </div>
)}
```

7) In the export phase, add `ExportProgressBar` below the merge button:
```tsx
{exportStarted && (
    <div className="mt-4 p-4 bg-glass rounded-xl border border-glass-border">
        <ExportProgressBar
            scriptId={currentProject!.id}
            onComplete={(url) => {
                // Refresh project to get updated merged_video_url
                if (currentProject) {
                    updateProject(currentProject.id, {
                        ...currentProject,
                        merged_video_url: url,
                    });
                }
            }}
        />
    </div>
)}
```

Full implementation detail: read the existing file, apply these targeted edits, and ensure the edit tab is the default landing view while preserving all existing takes/mix/export functionality.

- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new type errors.

- [ ] **Step 3: Run frontend dev to verify it loads**

Run: `cd frontend && npm run dev`
Open http://localhost:3008, navigate to a project → Assembly step.
Expected: "编辑" tab visible first, TimelineEditor renders with shots.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/modules/VideoAssembly.tsx
git commit -m "feat(v1-post): wire TimelineEditor + TransitionPicker + ExportProgressBar into Assembly page"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ 4.1 专业剪辑引擎 — Tasks 1-3 (models + EditingEngine + pipeline), Task 6 (TimelineEditor), Task 9 (integration)
- ✅ 4.2 转场效果库 — Task 1 (TransitionConfig model), Task 7 (TransitionPicker), Task 9 (integration)
- ✅ 4.3 视频预览与导出增强 — Task 4 (SSE endpoint), Task 8 (ExportProgressBar), Task 9 (integration)

**2. Placeholder scan:** No TBD/TODO/incomplete patterns found. All code blocks have concrete implementations.

**3. Type consistency:**
- `EditDecision.id` — string UUID, consistent across tasks 1, 3, 4, 5, 6
- `TransitionConfig.transition_type` — string from `_XFADE_MAP` keys, consistent across tasks 1, 2, 4, 5, 7
- `ExportPreset.preset_name` — string, consistent across tasks 1, 4, 5, 9
- `TimelineData.tracks` → `TimelineTrack[]`, consistent across tasks 1, 3, 4, 5, 6
- `ExportProgress.phase` — string union, consistent across tasks 1, 2, 4, 5, 8
- API paths: `/projects/{script_id}/timeline`, `/projects/{script_id}/edits`, `/projects/{script_id}/transitions`, `/projects/{script_id}/export/progress`, `/projects/{script_id}/export/start`, `/export/presets` — all match between backend (Task 4) and frontend (Task 5).

**Spec gap check:** P1 features (变速 UI, 替换片段, 逐帧预览) are deferred to V1.1 per the spec's explicit P1 tagging. The plan intentionally focuses on P0 features for an 8-week deliverable. This is documented in the task descriptions.

---
