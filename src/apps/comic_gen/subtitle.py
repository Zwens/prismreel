"""Subtitle generation from script data — deliberately not from ASR.

The dialogue text is authored in the app (StoryboardFrame.dialogue), the
TTS audio is synthesised by the app (StoryboardFrame.audio_url), and the
per-shot offset is already tracked (StoryboardFrame.dub_offset_ms). That is
strictly more information than speech recognition could recover, so running
ASR over our own output would only introduce transcription errors and cost.

ASR stays available as a V2 fallback for imported external audio.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional

from ...utils.media_probe import probe_duration
from .models import StoryboardFrame

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
