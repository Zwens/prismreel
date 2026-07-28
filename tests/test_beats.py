"""BGM 节拍检测的验证。

测速对音乐不是能保证正确的问题，最常见的失败是倍频歧义（锁到半速/倍速）。
所以这里用**合成点击轨**做基准——真值已知，才能量化算法到底准到什么程度，
而不是拿一段音乐"看着差不多"就算过。
"""

import os
import shutil
import subprocess

import pytest

from src.apps.comic_gen.beats import (
    BeatAnalysisError,
    analyze,
    snap_to_beats,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="节拍检测依赖 ffmpeg 解码"
)


def _click_track(path: str, bpm: float, seconds: float = 20.0) -> str:
    """合成一条已知 BPM 的点击轨：每拍一个 30ms 的 1kHz 短音。"""
    interval = 60.0 / bpm
    one = f"{path}.one.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.03:sample_rate=22050",
         "-af", f"apad=pad_dur={interval - 0.03}", "-t", str(interval), one],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-stream_loop", str(int(seconds / interval) + 1), "-i", one,
         "-t", str(seconds), path],
        check=True, capture_output=True,
    )
    os.remove(one)
    return path


@pytest.mark.parametrize("truth_bpm", [90.0, 128.0, 140.0])
def test_bpm_within_octave_tolerance(tmp_path, truth_bpm):
    """允许倍频误差——半速/倍速在音乐测速里是公认的等价答案。

    UI 提供了 ×2 / ÷2 按钮正是为此；这里断言的是"测到了正确的节拍族"。
    """
    track = _click_track(str(tmp_path / f"click_{truth_bpm}.wav"), truth_bpm)
    got = analyze(track)["bpm"]

    err = min(
        abs(got - truth_bpm),
        abs(got - truth_bpm * 2),
        abs(got - truth_bpm / 2),
    ) / truth_bpm
    assert err < 0.05, f"真值 {truth_bpm}，测得 {got}，含倍频容差后仍偏 {err:.1%}"


def test_analyze_reports_a_usable_grid(tmp_path):
    track = _click_track(str(tmp_path / "grid.wav"), 120.0, seconds=10.0)
    result = analyze(track)

    # 两者都为了 JSON 载荷整洁做了 4 位小数取整，所以只能比到那个精度
    assert result["beat_interval_s"] == pytest.approx(60.0 / result["bpm"], abs=1e-4)
    assert result["duration_s"] == pytest.approx(10.0, abs=0.2)
    assert len(result["beat_times"]) >= 2
    # 拍点必须单调递增且都落在音频时长内
    assert result["beat_times"] == sorted(result["beat_times"])
    assert result["beat_times"][-1] < result["duration_s"]


def test_missing_file_raises_analysis_error():
    with pytest.raises(BeatAnalysisError):
        analyze("does/not/exist.mp3")


def test_silence_raises_rather_than_returning_a_fake_bpm(tmp_path):
    """静音没有节奏信息。返回一个看似合理的 BPM 会让 UI 把假网格画出来。"""
    silent = str(tmp_path / "silence.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "anullsrc=r=22050:cl=mono", "-t", "5", silent],
        check=True, capture_output=True,
    )
    with pytest.raises(BeatAnalysisError):
        analyze(silent)


class TestSnapToBeats:
    """吸附只能剪短，不能补帧——渲染层没有凭空生成画面的能力。"""

    def test_snaps_down_to_nearest_whole_beat(self):
        assert snap_to_beats(2.1, 0.5) == pytest.approx(2.0)

    def test_rounding_up_falls_back_when_it_would_exceed_source(self):
        """1.9s 最接近 4 拍(2.0s)，但那要补 0.1s 的帧——只能退到 3 拍。

        这是"只能剪短"约束的直接后果，会让镜头比四舍五入的直觉更短一点。
        """
        assert snap_to_beats(1.9, 0.5) == pytest.approx(1.5)

    def test_never_exceeds_source_duration(self):
        # 2.4s 最接近 2.5s（5 拍），但那超过了原片长，只能退到 4 拍
        assert snap_to_beats(2.4, 0.5) == pytest.approx(2.0)
        assert snap_to_beats(2.4, 0.5) <= 2.4

    def test_shot_shorter_than_one_beat_is_left_alone(self):
        # 拉长到 1 拍需要补帧，做不到；保持原样而不是给出无法渲染的目标
        assert snap_to_beats(0.3, 0.5) == pytest.approx(0.3)

    def test_max_beats_caps_the_result(self):
        assert snap_to_beats(10.0, 0.5, max_beats=4) == pytest.approx(2.0)

    def test_zero_interval_is_a_no_op(self):
        assert snap_to_beats(3.0, 0.0) == pytest.approx(3.0)
