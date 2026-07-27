import os
import subprocess

import pytest

from src.apps.comic_gen.models import StoryboardFrame
from src.apps.comic_gen.subtitle import (
    MIN_CUE_S,
    RenderSegment,
    build_subtitle_cues,
)
from src.utils.system_check import get_ffmpeg_path

requires_ffmpeg = pytest.mark.skipif(not get_ffmpeg_path(), reason="ffmpeg not installed")


def _frame(fid, dialogue=None, offset_ms=0, audio_url=None):
    # StoryboardFrame requires id + scene_id (models.py:353-354); there is no
    # `description` field — the free-text field is `action_description`.
    return StoryboardFrame(
        id=fid,
        scene_id="sc1",
        dialogue=dialogue,
        dub_offset_ms=offset_ms,
        audio_url=audio_url,
    )


def _seg(fid, dur):
    return RenderSegment(frame_id=fid, video_path=f"/x/{fid}.mp4", duration_s=dur)


def test_cues_are_cumulative_across_shots():
    frames = [_frame("a", "第一句", audio_url="/a.mp3"), _frame("b", "第二句", audio_url="/b.mp3")]
    segs = [_seg("a", 5.0), _seg("b", 4.0)]
    cues = build_subtitle_cues(frames, segs, probe=lambda p: 2.0)

    assert len(cues) == 2
    assert cues[0].start_s == pytest.approx(0.0)
    assert cues[0].end_s == pytest.approx(2.0)
    assert cues[1].start_s == pytest.approx(5.0)  # 第二段从第一段结束处开始
    assert cues[1].end_s == pytest.approx(7.0)


def test_dub_offset_shifts_start():
    frames = [_frame("a", "台词", offset_ms=1500, audio_url="/a.mp3")]
    cues = build_subtitle_cues(frames, [_seg("a", 6.0)], probe=lambda p: 2.0)
    assert cues[0].start_s == pytest.approx(1.5)
    assert cues[0].end_s == pytest.approx(3.5)


def test_frames_without_dialogue_are_skipped_but_still_advance_clock():
    frames = [_frame("a"), _frame("b", "只有这句有台词", audio_url="/b.mp3")]
    segs = [_seg("a", 3.0), _seg("b", 4.0)]
    cues = build_subtitle_cues(frames, segs, probe=lambda p: 2.0)

    assert len(cues) == 1
    assert cues[0].start_s == pytest.approx(3.0)


def test_blank_dialogue_treated_as_absent():
    frames = [_frame("a", "   ")]
    assert build_subtitle_cues(frames, [_seg("a", 3.0)], probe=lambda p: 2.0) == []


def test_estimates_duration_when_no_audio():
    """没生成 TTS 时用阅读速度兜底，不能让字幕消失。"""
    frames = [_frame("a", "十个字的一句话啊")]  # 8 chars
    cues = build_subtitle_cues(frames, [_seg("a", 10.0)], probe=lambda p: 99.0)
    assert cues[0].end_s == pytest.approx(8 / 5.0)


def test_cue_clamped_to_shot_end():
    """TTS 比镜头长时，字幕不能溢出到下一镜头。"""
    frames = [_frame("a", "很长的台词", audio_url="/a.mp3")]
    cues = build_subtitle_cues(frames, [_seg("a", 3.0)], probe=lambda p: 10.0)
    assert cues[0].end_s == pytest.approx(3.0)


def test_minimum_cue_duration_enforced():
    """偏移把起点推到镜头末尾时，仍要保证可读的最短时长。"""
    frames = [_frame("a", "短", offset_ms=2900, audio_url="/a.mp3")]
    cues = build_subtitle_cues(frames, [_seg("a", 3.0)], probe=lambda p: 0.1)
    assert cues[0].end_s - cues[0].start_s == pytest.approx(MIN_CUE_S)


def test_probe_failure_falls_back_to_estimate():
    def boom(path):
        raise RuntimeError("ffprobe exploded")

    frames = [_frame("a", "十个字的一句话啊", audio_url="/a.mp3")]
    cues = build_subtitle_cues(frames, [_seg("a", 10.0)], probe=boom)
    assert cues[0].end_s == pytest.approx(8 / 5.0)


def test_probe_failure_is_logged_not_swallowed(caplog):
    """终审发现 #1/#2：静默的 `except Exception` 正是让"TTS 时长从未被测量"
    躲过十轮评审的机制。回退本身是对的，但必须留下痕迹。"""

    def boom(path):
        raise RuntimeError("ffprobe exploded")

    frames = [_frame("a", "十个字的一句话啊", audio_url="audio/a.mp3")]
    with caplog.at_level("WARNING", logger="src.apps.comic_gen.subtitle"):
        build_subtitle_cues(frames, [_seg("a", 10.0)], probe=boom)
    assert any(
        "audio/a.mp3" in r.message and r.levelname == "WARNING" for r in caplog.records
    ), f"probe 失败没有被记录：{[r.message for r in caplog.records]}"


def _write_real_audio(path, seconds):
    """A genuinely decodable audio file of a known length."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(
        [
            get_ffmpeg_path(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            str(seconds),
            "-c:a",
            "libmp3lame",
            path,
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return path


@requires_ffmpeg
def test_cue_uses_measured_tts_duration_not_the_estimate(tmp_path):
    """终审发现 #1：audio_url 是相对 output/ 存的，直接喂给 probe 恒抛异常，
    于是每条 cue 都退化成 len(text)/5.0。反向断言：给一个真实存在的 TTS
    文件，cue 时长必须等于实测时长、且不等于估算值。"""
    _write_real_audio(str(tmp_path / "audio" / "x.mp3"), 1.5)

    # 10 个字 -> 估算 2.0 s，与实测 1.5 s 明确可区分
    frames = [_frame("a", "一二三四五六七八九十", audio_url="audio/x.mp3")]
    cues = build_subtitle_cues(
        frames,
        [_seg("a", 5.0)],
        resolve=lambda u: str(tmp_path / u),
    )
    measured = cues[0].end_s - cues[0].start_s
    assert measured == pytest.approx(1.5, abs=0.1)
    assert measured != pytest.approx(2.0, abs=0.1)  # 不是朗读速率估算


@requires_ffmpeg
def test_default_resolve_is_identity_so_absolute_urls_still_work(tmp_path):
    """不传 resolve 时行为不变：绝对路径照旧能被探测到。"""
    p = _write_real_audio(str(tmp_path / "abs.mp3"), 1.5)
    frames = [_frame("a", "一二三四五六七八九十", audio_url=p)]
    cues = build_subtitle_cues(frames, [_seg("a", 5.0)])
    assert cues[0].end_s - cues[0].start_s == pytest.approx(1.5, abs=0.1)


def test_speaker_from_structured_dialogue():
    from src.apps.comic_gen.models import DialogueStructured

    f = _frame("a", "你好", audio_url="/a.mp3")
    f.dialogue_structured = DialogueStructured(speaker="林一", line="你好")
    cues = build_subtitle_cues([f], [_seg("a", 4.0)], probe=lambda p: 1.5)
    assert cues[0].speaker == "林一"


def test_segments_without_matching_frame_are_ignored():
    frames = [_frame("a", "台词", audio_url="/a.mp3")]
    segs = [_seg("ghost", 2.0), _seg("a", 4.0)]
    cues = build_subtitle_cues(frames, segs, probe=lambda p: 1.0)
    assert cues[0].start_s == pytest.approx(2.0)  # ghost 段仍然推进时钟


def test_cues_never_overlap_when_shot_shorter_than_min_cue():
    """分镜比 MIN_CUE_S 还短时，最小时长下限不得把 cue 推出分镜边界。

    重叠的字幕在 ASS 里会视觉堆叠。宁可闪一下也不越界。
    """
    frames = [
        _frame("a", "短", audio_url="/a.mp3"),
        _frame("b", "下一句", audio_url="/b.mp3"),
    ]
    segs = [_seg("a", 0.3), _seg("b", 5.0)]
    cues = build_subtitle_cues(frames, segs, probe=lambda p: 2.0)
    assert len(cues) == 2
    assert cues[0].end_s == pytest.approx(0.3)  # 截到分镜边界，而非 0.8
    assert cues[0].end_s <= cues[1].start_s


def test_zero_duration_shot_drops_cue_but_keeps_clock():
    """时长 0 的分镜（探测失败回退值）不该产出零长 cue，但时钟照常推进。"""
    frames = [
        _frame("a", "丢弃", audio_url="/a.mp3"),
        _frame("b", "保留", audio_url="/b.mp3"),
    ]
    segs = [_seg("a", 0.0), _seg("b", 5.0)]
    cues = build_subtitle_cues(frames, segs, probe=lambda p: 2.0)
    assert len(cues) == 1
    assert cues[0].text == "保留"
    assert cues[0].start_s == pytest.approx(0.0)


def test_offset_beyond_shot_is_pulled_back_inside():
    frames = [_frame("a", "台词", offset_ms=9000, audio_url="/a.mp3")]
    cues = build_subtitle_cues(frames, [_seg("a", 3.0)], probe=lambda p: 1.0)
    assert cues[0].start_s == pytest.approx(2.2)
    assert cues[0].end_s == pytest.approx(3.0)
