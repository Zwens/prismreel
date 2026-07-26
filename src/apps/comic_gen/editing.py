"""Final-render orchestration.

V-1 renders in two ffmpeg passes:

  Pass 1 (owned by pipeline.merge_videos)  concat + re-encode -> concat.mp4
  Pass 2 (this module)                     audio chain + subtitle burn -> final

A single filter_complex doing everything is the V2 target. Two passes are
chosen here because a variable-length concat graph combined with sidechain
audio and subtitle burning is very hard to debug when it fails, and V-1's
goal is a correct first film rather than the fastest possible render. The
audio chain and the subtitle burn share pass 2, so this costs one extra
encode, not two.
"""

import os
import subprocess
from typing import Callable, List, Optional

from ...utils import get_logger
from ...utils.media_probe import probe_dimensions, probe_duration
from .audio_mixer import build_audio_filter
from .models import Script
from .subtitle import (
    SUBTITLE_TEMPLATES,
    RenderSegment,
    build_subtitle_cues,
    render_ass,
)

logger = get_logger(__name__)

_PASS2_TIMEOUT_S = 1800


def escape_filter_path(path: str) -> str:
    """Escape a filesystem path for use inside an ffmpeg filter argument.

    Inside a filter, '\\' is an escape character and ':' separates options,
    so a Windows path like C:\\out\\s.ass must become C\\:/out/s.ass. This is
    the single most common cause of subtitle burn failures on Windows.
    """
    return path.replace("\\", "/").replace(":", "\\:")


def collect_render_segments(
    script: Script,
    *,
    resolve: Callable[[str], str],
    probe: Callable[[str], float] = probe_duration,
    exists: Callable[[str], bool] = os.path.exists,
) -> List[RenderSegment]:
    """Pick the video for each frame and measure it.

    This is the single source of truth for "which video does this shot
    use" — merge_videos's own concat-list construction must call this
    instead of keeping a second copy of the selection logic. Two
    implementations of the same selection rule can only drift apart; a
    dangling reference resolved one way for the video and another way for
    the subtitle timeline desyncs every cue after it.

    Selection precedence, exactly mirroring the old inline loop in
    merge_videos: dubbed video (if the file exists) > explicitly selected
    take (if it resolves to a real task with a url) > first completed
    take. A frame whose selected_video_id points at nothing is skipped —
    it is NOT silently replaced by some other take, because that would
    give the subtitle timeline one more shot than the concatenated video
    actually has.

    `resolve` maps a stored relative url to an absolute filesystem path
    (production passes _safe_resolve_path bound to "output"). `exists`
    checks whether that resolved path is present on disk (production
    passes os.path.exists; tests override it since they use fake paths).
    """
    segments: List[RenderSegment] = []

    for frame in script.frames:
        url = None

        if frame.dubbed_video_url:
            candidate = resolve(frame.dubbed_video_url)
            if exists(candidate):
                url = frame.dubbed_video_url
            else:
                logger.warning(
                    f"[RENDER] frame {frame.id}: dubbed video missing "
                    f"({candidate}); falling back to a take"
                )

        if url is None:
            if not frame.selected_video_id:
                task = next(
                    (
                        t
                        for t in script.video_tasks
                        if t.frame_id == frame.id and t.status == "completed" and t.video_url
                    ),
                    None,
                )
                url = task.video_url if task else None
            else:
                task = next(
                    (t for t in script.video_tasks if t.id == frame.selected_video_id), None
                )
                # A dangling selected_video_id skips the shot; it is NOT
                # silently replaced by some other take. Substituting here
                # would give the subtitle timeline one more shot than the
                # concatenated video has, desyncing everything after it.
                url = task.video_url if (task and task.video_url) else None
                if url is None:
                    logger.warning(
                        f"[RENDER] frame {frame.id}: selected video "
                        f"{frame.selected_video_id} not found or has no URL"
                    )

        if not url:
            logger.debug(f"[RENDER] frame {frame.id}: no usable video, skipping")
            continue

        abs_path = resolve(url)
        try:
            duration = probe(abs_path)
        except Exception as e:
            logger.warning(f"[RENDER] frame {frame.id}: duration probe failed ({e}); using 0")
            duration = 0.0

        segments.append(RenderSegment(frame_id=frame.id, video_path=abs_path, duration_s=duration))

    return segments


class RenderEngine:
    """Pass 2 of the render: audio mix + burned-in subtitles."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir

    def _write_ass(
        self, script: Script, segments: List[RenderSegment], concat_path: str
    ) -> Optional[str]:
        settings = script.subtitle_settings
        if not settings.enabled:
            return None

        # Carried-forward finding (2) from Task 5's review: a failed
        # duration probe in collect_render_segments silently substitutes
        # 0.0, which shifts every later cue earlier by the lost duration.
        # build_subtitle_cues only prevents a zero-length cue from being
        # emitted for the bad segment itself — it cannot recover the lost
        # time, so every cue after it would still drift. Shipping no
        # subtitles is safer than shipping a track that looks right for a
        # few cues and then silently desyncs.
        bad = [s.frame_id for s in segments if s.duration_s <= 0]
        if bad:
            logger.warning(
                f"[RENDER/SUB] {len(bad)} segment(s) have duration_s<=0 "
                f"(frame ids: {bad}); this would desync every subsequent "
                f"subtitle cue, so subtitle burn is skipped entirely for "
                f"this render"
            )
            return None

        cues = build_subtitle_cues(script.frames, segments)
        if not cues:
            logger.info("[RENDER/SUB] no dialogue found; skipping subtitle burn")
            return None

        style = settings.style_override or SUBTITLE_TEMPLATES.get(
            settings.template_id, SUBTITLE_TEMPLATES["douyin"]
        )
        try:
            play_res = probe_dimensions(concat_path)
        except Exception as e:
            logger.warning(f"[RENDER/SUB] dimension probe failed ({e}); assuming 1080x1920")
            play_res = (1080, 1920)

        ass_path = f"{os.path.splitext(concat_path)[0]}.ass"
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(render_ass(cues, style, play_res=play_res))
        logger.info(f"[RENDER/SUB] wrote {len(cues)} cues -> {os.path.basename(ass_path)}")
        return ass_path

    def finalize(
        self,
        script: Script,
        concat_path: str,
        *,
        ffmpeg_path: str,
        segments: List[RenderSegment],
        bgm_abs_path: Optional[str] = None,
    ) -> Optional[str]:
        """Apply the audio chain and subtitle burn to `concat_path`.

        Returns the path of the finished file, or None when nothing needed
        doing (caller then keeps the concat output as-is).
        """
        ass_path = self._write_ass(script, segments, concat_path)
        has_bgm = bool(bgm_abs_path and os.path.exists(bgm_abs_path))

        mix = script.mix_settings or {"dialogue": 100, "bgm": 35, "sfx": 60}
        audio_filter = build_audio_filter(
            dialogue_level=int(mix.get("dialogue", 100)),
            bgm_level=int(mix.get("bgm", 35)),
            has_bgm=has_bgm,
            ducking=True,
            normalize=True,
        )

        out_path = concat_path.replace(".mp4", "_final.mp4")
        cmd = [ffmpeg_path, "-y", "-i", concat_path]
        if has_bgm:
            cmd += ["-stream_loop", "-1", "-i", bgm_abs_path]
        cmd += ["-filter_complex", audio_filter]

        if ass_path:
            cmd += ["-vf", f"ass='{escape_filter_path(ass_path)}'"]
            cmd += ["-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "copy"]

        cmd += [
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            out_path,
        ]

        logger.info(
            f"[RENDER] pass 2 — bgm={has_bgm} subtitles={bool(ass_path)} " f"ducking=on loudnorm=on"
        )
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=_PASS2_TIMEOUT_S)
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="replace")[:600] if e.stderr else ""
            logger.error(f"[RENDER] pass 2 failed: {stderr}")
            return None
        except subprocess.TimeoutExpired:
            logger.error("[RENDER] pass 2 timed out")
            return None

        if not os.path.exists(out_path):
            logger.error(f"[RENDER] pass 2 produced no output at {out_path}")
            return None
        return out_path
