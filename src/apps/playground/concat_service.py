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

from .service import VIDEO_OUTPUT_DIR
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
