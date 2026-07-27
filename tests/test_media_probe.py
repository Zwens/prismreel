import os
import subprocess

import pytest

from src.utils.media_probe import (
    MediaProbeError,
    has_audio_stream,
    probe_dimensions,
    probe_duration,
)
from src.utils.system_check import get_ffmpeg_path, get_ffprobe_path

requires_ffmpeg = pytest.mark.skipif(
    not get_ffmpeg_path() or not get_ffprobe_path(),
    reason="ffmpeg/ffprobe not installed",
)


def test_get_ffprobe_path_returns_something_or_none():
    p = get_ffprobe_path()
    assert p is None or os.path.exists(p) or os.path.basename(p).startswith("ffprobe")


def test_probe_missing_file_raises():
    with pytest.raises(MediaProbeError):
        probe_duration("/definitely/not/here.mp4")


@pytest.fixture
def sample_video(tmp_path):
    """2 秒 320x240 测试视频 + 静音音轨。"""
    ff = get_ffmpeg_path()
    if not ff:
        pytest.skip("ffmpeg not installed")
    out = str(tmp_path / "sample.mp4")
    subprocess.run(
        [
            ff, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-shortest", "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
            out,
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return out


@requires_ffmpeg
def test_probe_duration(sample_video):
    assert probe_duration(sample_video) == pytest.approx(2.0, abs=0.2)


@requires_ffmpeg
def test_probe_dimensions(sample_video):
    assert probe_dimensions(sample_video) == (320, 240)


@pytest.fixture
def silent_video(tmp_path):
    """默认 Silent Mode 产出的形状：完全没有音频流。"""
    ff = get_ffmpeg_path()
    if not ff:
        pytest.skip("ffmpeg not installed")
    out = str(tmp_path / "silent.mp4")
    subprocess.run(
        [
            ff, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "2",
            out,
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return out


@requires_ffmpeg
def test_has_audio_stream_true(sample_video):
    assert has_audio_stream(sample_video) is True


@requires_ffmpeg
def test_has_audio_stream_false_for_video_without_audio(silent_video):
    assert has_audio_stream(silent_video) is False


def test_has_audio_stream_is_false_when_probe_fails():
    """探测失败时保守返回 False —— 调用方会合成静音源，代价远小于让
    pass 2 因为 [0:a] 匹配不到流而整体失败。"""
    assert has_audio_stream("/definitely/not/here.mp4") is False
