"""Subtitle generation from script data — deliberately not from ASR.

The dialogue text is authored in the app (StoryboardFrame.dialogue), the
TTS audio is synthesised by the app (StoryboardFrame.audio_url), and the
per-shot offset is already tracked (StoryboardFrame.dub_offset_ms). That is
strictly more information than speech recognition could recover, so running
ASR over our own output would only introduce transcription errors and cost.

ASR stays available as a V2 fallback for imported external audio.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from ...utils.media_probe import probe_duration
from .models import StoryboardFrame, SubtitleStyle

# Comfortable Chinese subtitle reading rate. Also the fallback cue length
# when no TTS audio exists yet.
CHARS_PER_SECOND = 5.0
# Below this a cue flashes past unreadably.
MIN_CUE_S = 0.8


@dataclass
class RenderSegment:
    """One shot as it will appear in the concatenated output."""

    frame_id: str
    video_path: str
    duration_s: float


@dataclass
class SubtitleCue:
    start_s: float
    end_s: float
    text: str
    speaker: Optional[str] = None


def _estimate_duration(text: str) -> float:
    return max(MIN_CUE_S, len(text) / CHARS_PER_SECOND)


def _spoken_duration(frame: StoryboardFrame, text: str, probe: Callable[[str], float]) -> float:
    """Real TTS length when available, reading-rate estimate otherwise."""
    if not frame.audio_url:
        return _estimate_duration(text)
    try:
        return probe(frame.audio_url)
    except Exception:
        # A missing or unreadable audio file must not drop the subtitle.
        return _estimate_duration(text)


def build_subtitle_cues(
    frames: List[StoryboardFrame],
    segments: List[RenderSegment],
    *,
    probe: Callable[[str], float] = probe_duration,
) -> List[SubtitleCue]:
    """Map dialogue onto the concatenated timeline.

    `segments` must be in render order and carry real measured durations —
    the cumulative sum of those durations is the output timeline. Segments
    with no matching frame still advance the clock so later cues stay aligned.
    """
    by_id = {f.id: f for f in frames}
    cues: List[SubtitleCue] = []
    offset = 0.0

    for seg in segments:
        frame = by_id.get(seg.frame_id)
        if frame is None:
            offset += seg.duration_s
            continue

        text = (frame.dialogue or "").strip()
        if not text:
            offset += seg.duration_s
            continue

        shot_end = offset + seg.duration_s
        start = offset + (frame.dub_offset_ms or 0) / 1000.0
        start = min(start, max(offset, shot_end - MIN_CUE_S))

        end = start + _spoken_duration(frame, text, probe)
        end = min(end, shot_end)
        if end - start < MIN_CUE_S:
            # Prefer a short flash over a cue that runs past its shot: cues
            # that overlap stack visually in ASS. A shot shorter than
            # MIN_CUE_S cannot hold a readable subtitle either way, and the
            # cumulative clock advances by shot_end regardless — so letting
            # the floor win here would desync every cue after it.
            end = min(start + MIN_CUE_S, shot_end)
        if end <= start:
            # Zero-length shot — reachable when a duration probe fails and
            # the caller substitutes 0.0. A cue with no duration is
            # meaningless and renders as an artefact.
            offset = shot_end
            continue

        speaker = frame.dialogue_structured.speaker if frame.dialogue_structured else None
        cues.append(SubtitleCue(start_s=start, end_s=end, text=text, speaker=speaker))
        offset = shot_end

    return cues


# ----------------------------------------------------------------------
# ASS rendering
# ----------------------------------------------------------------------

SUBTITLE_TEMPLATES: Dict[str, SubtitleStyle] = {
    # Large, heavy, high-contrast. margin_v clears the platform action rail.
    "douyin": SubtitleStyle(
        font_family="Alibaba PuHuiTi",
        font_size=64,
        primary_color="#FFFFFF",
        outline_color="#000000",
        outline_width=4,
        bold=True,
        alignment=2,
        margin_v=180,
        chars_per_line=18,
        max_lines=2,
    ),
    # Restrained, thinner outline, sits lower — reads as film subtitling.
    "cinematic": SubtitleStyle(
        font_family="Alibaba PuHuiTi",
        font_size=52,
        primary_color="#F5F5F5",
        outline_color="#000000",
        outline_width=2,
        bold=False,
        alignment=2,
        margin_v=90,
        chars_per_line=22,
        max_lines=2,
    ),
}


def _hex_to_ass_color(hex_rgb: str) -> str:
    """#RRGGBB -> &HAABBGGRR with AA=00 (opaque).

    ASS stores colour as BGR, not RGB. Getting this backwards silently swaps
    red and blue, which is easy to miss on white text and obvious on any
    coloured template.
    """
    h = hex_rgb.lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _ass_time(seconds: float) -> str:
    """H:MM:SS.CC — ASS uses centiseconds, not milliseconds.

    Truncates rather than rounds (3.456s -> 3.45, not 3.46), matching how
    ASS timecodes are conventionally derived from cue boundaries. A small
    epsilon absorbs float representation error (e.g. 0.29 * 100 landing on
    28.999999999999996) without turning into rounding.
    """
    if seconds < 0:
        seconds = 0.0
    total_cs = int(seconds * 100 + 1e-6)
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def wrap_cjk(text: str, per_line: int, max_lines: int) -> str:
    """Hard-wrap by character count, joining lines with the ASS break \\N.

    `text` may already contain authored \\N breaks. Each authored line is
    wrapped independently and the cue as a whole is then capped at
    max_lines, so an authored break can neither escape wrapping nor
    multiply the line budget.

    CJK has no word boundaries, so counting characters is the correct
    strategy here — a word-based wrapper would never break.
    """
    text = text.strip()
    if per_line <= 0:
        return text
    # max_lines is user-overridable via SubtitleStyle; 0 would make the
    # truncation branch index an empty list.
    max_lines = max(1, max_lines)

    lines: List[str] = []
    for authored in text.split(r"\N"):
        if not authored:
            continue
        lines.extend(authored[i : i + per_line] for i in range(0, len(authored), per_line))

    if not lines:
        return text
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        lines[-1] = (last[:-1] if len(last) >= per_line else last) + "…"
    return r"\N".join(lines)


def _escape_ass_text(text: str) -> str:
    """Braces delimit override tags; literal braces must be escaped."""
    return text.replace("{", r"\{").replace("}", r"\}")


def render_ass(
    cues: List[SubtitleCue],
    style: SubtitleStyle,
    *,
    play_res: Tuple[int, int],
) -> str:
    """Render cues to an ASS subtitle document.

    play_res must match the output video resolution or font sizes will be
    scaled by the renderer and come out wrong.
    """
    width, height = play_res
    primary = _hex_to_ass_color(style.primary_color)
    outline = _hex_to_ass_color(style.outline_color)
    bold = -1 if style.bold else 0

    head = [
        "[Script Info]",
        "; Generated by PrismReel Studio",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: Default,{style.font_family},{style.font_size},"
            f"{primary},&H000000FF,{outline},&H80000000,"
            f"{bold},0,0,0,100,100,0,0,1,{style.outline_width},0,"
            f"{style.alignment},60,60,{style.margin_v},1"
        ),
        "",
        "[Events]",
        ("Format: Layer, Start, End, Style, Name, MarginL, MarginR, " "MarginV, Effect, Text"),
    ]

    events = []
    for cue in cues:
        text = _escape_ass_text(cue.text).replace("\r\n", "\n").replace("\n", r"\N")
        # Always wrap. wrap_cjk handles authored \N breaks itself — skipping
        # the call when a break is present would let a long authored line
        # render unwrapped and overflow the frame.
        text = wrap_cjk(text, style.chars_per_line, style.max_lines)
        events.append(
            f"Dialogue: 0,{_ass_time(cue.start_s)},{_ass_time(cue.end_s)},"
            f"Default,,0,0,0,,{text}"
        )

    return "\n".join(head + events) + "\n"


# ----------------------------------------------------------------------
# SRT rendering
# ----------------------------------------------------------------------


def _srt_time(seconds: float) -> str:
    """HH:MM:SS,mmm — SRT uses milliseconds and a comma separator."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def render_srt(cues: List[SubtitleCue]) -> str:
    """Plain SRT for import into external editors."""
    blocks = []
    for i, cue in enumerate(cues, start=1):
        text = cue.text.replace(r"\N", "\n")
        blocks.append(f"{i}\n{_srt_time(cue.start_s)} --> {_srt_time(cue.end_s)}\n{text}\n")
    return "\n".join(blocks)
