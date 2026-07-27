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
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...utils import get_logger
from ...utils.media_probe import has_audio_stream, probe_dimensions, probe_duration
from ...utils.safe_path import safe_resolve_path
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

# A silent stereo source, used as the dialogue input when the concatenated
# video has no audio stream of its own (the pipeline's default Silent Mode).
_SILENT_SOURCE = "anullsrc=r=48000:cl=stereo"

# Characters allowed in a generated .ass filename. Anything else is
# transliterated to "_" — see _ass_filename.
_ASS_NAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def escape_filter_path(path: str) -> str:
    """Escape a filesystem path for use inside an ffmpeg filter argument.

    Inside a filter, '\\' is an escape character, ':' separates options and
    ',' ';' '[' ']' delimit the graph, so a Windows path like C:\\out\\s.ass
    must become C\\:/out/s.ass. This is the single most common cause of
    subtitle burn failures on Windows.

    Order matters: the quote is escaped first, otherwise the backslashes
    inserted by the later replacements would themselves be escaped.

    IMPORTANT — this cannot rescue every path. A literal "'" is not
    expressible inside an ffmpeg filter argument at all: \\' , '\\'' and
    \\\\' were all measured against ffmpeg 8.1.1 and every one of them is
    swallowed before libass sees it. That is why finalize never puts a
    directory it does not control into the filter string (see _ass_filename
    and the cwd= argument on the pass-2 subprocess call) — this function
    only ever receives a filename this module generated.
    """
    p = path.replace("\\", "/")
    p = p.replace("'", "\\'")
    p = p.replace(":", "\\:")
    return p.replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")


def _ass_filename(concat_path: str) -> str:
    """Derive a filter-safe .ass filename from the concat output name."""
    stem = os.path.splitext(os.path.basename(concat_path))[0]
    return f"{_ASS_NAME_SAFE_RE.sub('_', stem)}.ass"


@dataclass
class FinalizeResult:
    """What pass 2 actually did.

    finalize used to return Optional[str], so four independent paths could
    silently drop the subtitle track — settings disabled, a zero-duration
    segment, no dialogue, or any ffmpeg failure — with nothing but a log
    line to show for it. The caller could not tell a correct film from a
    subtitle-less one. A return value carries that; an instance attribute
    would not, because RenderEngine is constructed and discarded inline
    (RenderEngine().finalize(...)) and would invite stale state.
    """

    path: Optional[str] = None
    subtitles_burned: bool = False
    bgm_applied: bool = False
    loudnorm_applied: bool = False
    skip_reason: Optional[str] = None
    ass_path: Optional[str] = None

    def as_report(self) -> Dict[str, Any]:
        """Compact, persistable summary for Script.last_render_report."""
        return {
            "subtitles": (
                "burned" if self.subtitles_burned else f"skipped:{self.skip_reason or 'unknown'}"
            ),
            "bgm": "applied" if self.bgm_applied else "none",
            "loudnorm": "applied" if self.loudnorm_applied else "skipped",
        }


def _resolve_or_none(
    resolve: Callable[[str], str], url: str, frame_id: str, what: str
) -> Optional[str]:
    """Resolve a stored url, returning None instead of raising.

    A url that escapes the output directory — corrupted or hand-edited
    project data — must degrade to dropping one shot, never abort the
    export. merge_videos calls collect_render_segments before pass 1, so an
    unguarded raise anywhere in the selection path kills the whole render.
    Every resolve() call site in this module must go through here.
    """
    try:
        return resolve(url)
    except Exception as e:
        logger.warning(f"[RENDER] frame {frame_id}: unusable {what} url {url!r} ({e})")
        return None


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
            candidate = _resolve_or_none(resolve, frame.dubbed_video_url, frame.id, "dubbed")
            if candidate and exists(candidate):
                url = frame.dubbed_video_url
            else:
                logger.warning(
                    f"[RENDER] frame {frame.id}: dubbed video unusable "
                    f"({frame.dubbed_video_url}); falling back to a take"
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

        abs_path = _resolve_or_none(resolve, url, frame.id, "video")
        if abs_path is None:
            continue

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
    ) -> Tuple[Optional[str], Optional[str]]:
        """Write the subtitle track, or explain why there isn't one.

        Returns (ass_path, skip_reason); exactly one of the two is set.
        """
        settings = script.subtitle_settings
        if not settings.enabled:
            return None, "disabled"

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
            return None, f"zero_duration_segments:{','.join(bad)}"

        # frame.audio_url is stored relative to the output dir; without this
        # resolve every TTS probe fails and every cue silently degrades to a
        # reading-rate estimate.
        cues = build_subtitle_cues(
            script.frames,
            segments,
            resolve=lambda u: safe_resolve_path(self.output_dir, u),
        )
        if not cues:
            logger.info("[RENDER/SUB] no dialogue found; skipping subtitle burn")
            return None, "no_dialogue"

        style = settings.style_override or SUBTITLE_TEMPLATES.get(
            settings.template_id, SUBTITLE_TEMPLATES["douyin"]
        )
        try:
            play_res = probe_dimensions(concat_path)
        except Exception as e:
            logger.warning(f"[RENDER/SUB] dimension probe failed ({e}); assuming 1080x1920")
            play_res = (1080, 1920)

        # The filename is sanitised because it is the only part of the path
        # that reaches ffmpeg's filter parser (finalize runs pass 2 with
        # cwd set to this directory). The directory is the user's install
        # location and may legitimately contain an apostrophe.
        ass_path = os.path.join(os.path.dirname(concat_path), _ass_filename(concat_path))
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(render_ass(cues, style, play_res=play_res))
        logger.info(f"[RENDER/SUB] wrote {len(cues)} cues -> {os.path.basename(ass_path)}")
        return ass_path, None

    def finalize(
        self,
        script: Script,
        concat_path: str,
        *,
        ffmpeg_path: str,
        segments: List[RenderSegment],
        bgm_abs_path: Optional[str] = None,
    ) -> FinalizeResult:
        """Apply the audio chain and subtitle burn to `concat_path`.

        Returns a FinalizeResult describing what actually happened. Its
        `path` is None when pass 2 produced nothing (caller then keeps the
        concat output as-is); the remaining fields say whether subtitles,
        BGM and loudness normalisation really made it into the film.
        """
        ass_path, sub_skip = self._write_ass(script, segments, concat_path)
        has_bgm = bool(bgm_abs_path and os.path.exists(bgm_abs_path))

        # The generation pipeline's default is Silent Mode, so the concat
        # output routinely has no audio stream at all. Referencing [0:a]
        # then aborts the whole of pass 2 — BGM, loudnorm and subtitles
        # together — and the caller still reports success.
        dialogue_present = has_audio_stream(concat_path)

        mix = script.mix_settings or {"dialogue": 100, "bgm": 35, "sfx": 60}

        # Input order: 0 = concat, 1 = bgm (audio_mixer's documented
        # convention), then the synthetic silence last so the bgm index
        # stays fixed at 1.
        inputs: List[str] = ["-i", concat_path]
        next_index = 1
        if has_bgm:
            inputs = ["-i", concat_path, "-stream_loop", "-1", "-i", bgm_abs_path]
            next_index = 2
        dialogue_label = "0:a"
        if not dialogue_present:
            inputs += ["-f", "lavfi", "-i", _SILENT_SOURCE]
            dialogue_label = f"{next_index}:a"
            logger.info(
                "[RENDER] concat output has no audio stream (Silent Mode); "
                f"feeding the mix from a synthetic silent source [{dialogue_label}]"
            )

        audio_filter = build_audio_filter(
            dialogue_level=int(mix.get("dialogue", 100)),
            bgm_level=int(mix.get("bgm", 35)),
            has_bgm=has_bgm,
            ducking=True,
            normalize=True,
            dialogue_label=dialogue_label,
        )

        out_path = concat_path.replace(".mp4", "_final.mp4")

        def _build_cmd(burn: bool) -> List[str]:
            cmd = [ffmpeg_path, "-y", *inputs, "-filter_complex", audio_filter]
            if burn:
                # Only the basename goes into the filter string; pass 2 runs
                # with cwd set to the .ass directory. An apostrophe in the
                # install path (C:\Users\O'Brien\...) cannot be escaped in an
                # ffmpeg filter argument by any known form, so the directory
                # must never appear there.
                cmd += ["-vf", f"ass='{escape_filter_path(os.path.basename(ass_path))}'"]
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
            return cmd

        run_cwd = os.path.dirname(ass_path) if ass_path else None

        def _run(burn: bool) -> Optional[str]:
            """Run pass 2; returns stderr on failure, None on success."""
            try:
                subprocess.run(
                    _build_cmd(burn),
                    check=True,
                    capture_output=True,
                    timeout=_PASS2_TIMEOUT_S,
                    cwd=run_cwd,
                )
            except subprocess.CalledProcessError as e:
                return e.stderr.decode(errors="replace")[-600:] if e.stderr else "(no stderr)"
            except subprocess.TimeoutExpired:
                return "timed out"
            return None

        logger.info(
            f"[RENDER] pass 2 — bgm={has_bgm} subtitles={bool(ass_path)} "
            f"dialogue_audio={dialogue_present} ducking=on loudnorm=on"
        )

        burned = bool(ass_path)
        err = _run(burn=burned)
        if err and burned:
            # Do not let a subtitle failure take the BGM and the loudness
            # normalisation down with it: retry once without the burn.
            logger.error(f"[RENDER] pass 2 with subtitle burn failed: {err}")
            logger.warning("[RENDER] retrying pass 2 without the subtitle burn")
            burned = False
            sub_skip = "burn_failed"
            err = _run(burn=False)

        if err:
            logger.error(f"[RENDER] pass 2 failed: {err}")
            return FinalizeResult(path=None, skip_reason=sub_skip or "render_failed")

        if not os.path.exists(out_path):
            logger.error(f"[RENDER] pass 2 produced no output at {out_path}")
            return FinalizeResult(path=None, skip_reason=sub_skip or "render_failed")

        return FinalizeResult(
            path=out_path,
            subtitles_burned=burned,
            bgm_applied=has_bgm,
            loudnorm_applied=True,
            skip_reason=None if burned else sub_skip,
            ass_path=ass_path if burned else None,
        )
