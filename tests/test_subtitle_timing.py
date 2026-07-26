import pytest

from src.apps.comic_gen.models import StoryboardFrame
from src.apps.comic_gen.subtitle import (
    MIN_CUE_S,
    RenderSegment,
    build_subtitle_cues,
)


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
