"""Thin ffprobe wrapper for duration and dimension lookups.

Subtitle timing needs the real duration of each rendered shot and of each
TTS audio file; the ASS header needs the output resolution.
"""

import json
import os
import subprocess
from typing import Tuple

from .system_check import get_ffprobe_path

_TIMEOUT_S = 30


class MediaProbeError(Exception):
    """ffprobe could not read the file."""


def _run_ffprobe(path: str, args: list) -> dict:
    if not os.path.exists(path):
        raise MediaProbeError(f"File not found: {path}")

    ffprobe = get_ffprobe_path()
    if not ffprobe:
        raise MediaProbeError(
            "ffprobe not found. It ships with ffmpeg — install ffmpeg and restart."
        )

    cmd = [ffprobe, "-v", "error", "-print_format", "json", *args, path]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise MediaProbeError(f"ffprobe timed out on {path}") from e

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[:400]
        raise MediaProbeError(f"ffprobe failed on {path}: {stderr}")

    try:
        return json.loads(result.stdout.decode(errors="replace"))
    except json.JSONDecodeError as e:
        raise MediaProbeError(f"ffprobe returned invalid JSON for {path}") from e


def probe_duration(path: str) -> float:
    """Duration in seconds."""
    data = _run_ffprobe(path, ["-show_entries", "format=duration"])
    raw = (data.get("format") or {}).get("duration")
    if raw is None:
        raise MediaProbeError(f"No duration reported for {path}")
    try:
        return float(raw)
    except (TypeError, ValueError) as e:
        raise MediaProbeError(f"Unparseable duration {raw!r} for {path}") from e


def has_audio_stream(path: str) -> bool:
    """Whether the file carries at least one audio stream.

    The generation pipeline's default is Silent Mode, so a concatenated
    film routinely has no audio stream at all. An audio filter graph that
    references [0:a] on such a file makes ffmpeg abort with "matches no
    streams", taking the BGM, the loudness normalisation and the subtitle
    burn down with it.

    Returns False when the probe itself fails: the caller's safe response
    to "unknown" is the same as to "no audio" (synthesise a silent track),
    whereas guessing True re-creates the failure this exists to prevent.
    """
    try:
        data = _run_ffprobe(
            path,
            ["-select_streams", "a", "-show_entries", "stream=codec_type"],
        )
    except MediaProbeError:
        return False
    return bool(data.get("streams"))


def probe_dimensions(path: str) -> Tuple[int, int]:
    """(width, height) of the first video stream."""
    data = _run_ffprobe(
        path,
        ["-select_streams", "v:0", "-show_entries", "stream=width,height"],
    )
    streams = data.get("streams") or []
    if not streams:
        raise MediaProbeError(f"No video stream in {path}")
    w, h = streams[0].get("width"), streams[0].get("height")
    if not w or not h:
        raise MediaProbeError(f"Missing dimensions in {path}")
    return int(w), int(h)
