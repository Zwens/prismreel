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
