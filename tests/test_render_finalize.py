"""Production-call-site tests for RenderEngine.finalize.

The whole point of this file is the seam the branch's other ~78 tests do not
cover: every pass-2 test so far either exercised a pure function or hand-rolled
its own ffmpeg command line. Three shipped defects (silent-mode input with no
audio stream, an apostrophe in the install path, TTS duration never actually
measured) lived exactly in the gap between "the pure function is tested" and
"the thing production calls is tested". These tests call finalize itself.
"""

import os
import subprocess

import pytest

from src.apps.comic_gen.editing import RenderEngine
from src.apps.comic_gen.models import Script, StoryboardFrame
from src.apps.comic_gen.subtitle import RenderSegment
from src.utils.media_probe import has_audio_stream
from src.utils.system_check import get_ffmpeg_path

requires_ffmpeg = pytest.mark.skipif(not get_ffmpeg_path(), reason="ffmpeg not installed")

FF = get_ffmpeg_path()


# ----------------------------------------------------------------------
# fixtures / helpers
# ----------------------------------------------------------------------


def _run(args, cwd=None):
    subprocess.run(args, check=True, capture_output=True, timeout=180, cwd=cwd)


def _make_video(path, seconds=2.0, with_audio=True, size="320x240"):
    """A real mp4. with_audio=False reproduces the pipeline's default
    Silent Mode output: a video file with no audio stream at all."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmd = [FF, "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate=25"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", str(seconds), path]
    _run(cmd)
    return path


def _make_audio(path, seconds=1.5):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _run(
        [
            FF,
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
        ]
    )
    return path


def _frame(fid, dialogue=None, audio_url=None):
    return StoryboardFrame(id=fid, scene_id="sc1", dialogue=dialogue, audio_url=audio_url)


def _script(frames, subtitles=True):
    s = Script(
        id="s1",
        title="t",
        original_text="x",
        frames=frames,
        created_at=0.0,
        updated_at=0.0,
    )
    s.subtitle_settings.enabled = subtitles
    return s


def _seg(fid, dur):
    return RenderSegment(frame_id=fid, video_path=f"/x/{fid}.mp4", duration_s=dur)


# ----------------------------------------------------------------------
# 终审发现 #2 —— 拼接产物没有音轨时，pass 2 整体失败
# ----------------------------------------------------------------------


@requires_ffmpeg
def test_finalize_succeeds_on_a_video_with_no_audio_stream(tmp_path):
    """生成管线的默认模式（Silent Mode, generate_audio=False）产出的分镜就没有
    音轨，拼接产物因此也没有。build_audio_filter 无条件引用 [0:a]，pass 2 直接
    报 "matches no streams" 退出 —— BGM、响度归一、烧录字幕一起丢，成片退回
    修复前的哑片状态，而 merge_videos 仍然报告成功。"""
    concat = _make_video(str(tmp_path / "video" / "concat.mp4"), with_audio=False)
    assert has_audio_stream(concat) is False  # 前提

    script = _script([_frame("f1", "第一句台词")])
    res = RenderEngine(output_dir=str(tmp_path)).finalize(
        script, concat, ffmpeg_path=FF, segments=[_seg("f1", 2.0)]
    )
    assert res.path is not None, "pass 2 在无音轨输入上失败了"
    assert has_audio_stream(res.path) is True, "成片必须真的带上音轨"
    assert res.subtitles_burned is True
    assert res.loudnorm_applied is True


@requires_ffmpeg
def test_finalize_mixes_bgm_into_a_video_with_no_audio_stream(tmp_path):
    """无音轨 + 有 BGM：ducking 分支同样无条件引用 [0:a]，同样失败。"""
    concat = _make_video(str(tmp_path / "video" / "concat.mp4"), with_audio=False)
    bgm = _make_audio(str(tmp_path / "presets" / "bgm.mp3"), seconds=3.0)

    script = _script([_frame("f1", "第一句台词")])
    res = RenderEngine(output_dir=str(tmp_path)).finalize(
        script, concat, ffmpeg_path=FF, segments=[_seg("f1", 2.0)], bgm_abs_path=bgm
    )
    assert res.path is not None
    assert res.bgm_applied is True
    assert has_audio_stream(res.path) is True


@requires_ffmpeg
def test_finalize_still_works_when_input_has_audio(tmp_path):
    """回归：有音轨的正常路径不能被无音轨的兜底改坏。"""
    concat = _make_video(str(tmp_path / "video" / "concat.mp4"), with_audio=True)
    script = _script([_frame("f1", "第一句台词")])
    res = RenderEngine(output_dir=str(tmp_path)).finalize(
        script, concat, ffmpeg_path=FF, segments=[_seg("f1", 2.0)]
    )
    assert res.path is not None
    assert has_audio_stream(res.path) is True


# ----------------------------------------------------------------------
# 终审发现 #4 —— 敌意路径字符
# ----------------------------------------------------------------------


@pytest.mark.parametrize("dirname", ["plain", "O'Brien", "a,b", "x[1]"])
@requires_ffmpeg
def test_finalize_burns_subtitles_from_a_hostile_install_path(tmp_path, dirname):
    """终审发现 #4（已实跑复现）：应用装在 C:\\Users\\O'Brien\\... 下时，撇号
    被 ffmpeg 的滤镜解析层吞掉，libass fopen 失败，整个 pass 2 退出 —— 这台
    机器上每一次导出都永久丢字幕 + BGM + 响度归一。逗号/方括号是另一种破法。

    注意：撇号在 ffmpeg 滤镜参数里**无法**用任何转义写法表达（\\' / '\\'' /
    \\\\' 实测全部被吞），所以 finalize 必须让 .ass 的目录部分根本不进滤镜
    字符串 —— 目录是用户的安装位置，我们无权决定它长什么样。"""
    root = tmp_path / dirname
    concat = _make_video(str(root / "video" / "concat.mp4"), with_audio=True)

    script = _script([_frame("f1", "第一句台词")])
    res = RenderEngine(output_dir=str(root)).finalize(
        script, concat, ffmpeg_path=FF, segments=[_seg("f1", 2.0)]
    )
    assert res.path is not None, "pass 2 在敌意路径下失败了"
    assert res.subtitles_burned is True, f"字幕没有烧进去：{res.skip_reason}"


# ----------------------------------------------------------------------
# 终审发现 #1 —— 真实 TTS 时长必须一路走到 cue（生产接线，不是纯函数）
# ----------------------------------------------------------------------


@requires_ffmpeg
def test_finalize_writes_cues_using_the_real_tts_duration(tmp_path):
    """audio_url 是相对 output/ 存的（audio.py: os.path.relpath(path, "output")）。
    _write_ass 必须把它解析到 RenderEngine.output_dir 之下再探测，否则每条 cue
    都退化成 len(text)/5.0 —— 这是纯函数测试测不到的那一层接线。"""
    out_root = tmp_path / "output"
    concat = _make_video(str(out_root / "video" / "concat.mp4"), seconds=6.0, with_audio=True)
    # 真实 1.5 s 的 TTS 文件，放在 audio.py 实际会写的位置
    _make_audio(str(out_root / "audio" / "dialogue" / "f1.mp3"), seconds=1.5)

    # 10 个字 -> 朗读速率估算 2.0 s，与实测 1.5 s 明确可区分
    frame = _frame(
        "f1", "一二三四五六七八九十", audio_url=os.path.join("audio", "dialogue", "f1.mp3")
    )
    script = _script([frame])

    res = RenderEngine(output_dir=str(out_root)).finalize(
        script, concat, ffmpeg_path=FF, segments=[_seg("f1", 6.0)]
    )
    assert res.subtitles_burned is True
    assert res.ass_path and os.path.exists(res.ass_path)

    dialogue_lines = [
        ln
        for ln in open(res.ass_path, encoding="utf-8").read().splitlines()
        if ln.startswith("Dialogue:")
    ]
    assert len(dialogue_lines) == 1
    end_cs = dialogue_lines[0].split(",")[2]  # H:MM:SS.CC
    # 0:00:01.50 (实测) 而不是 0:00:02.00 (估算)
    assert end_cs.startswith("0:00:01.5"), f"cue 用的不是实测 TTS 时长：{end_cs}"


# ----------------------------------------------------------------------
# 终审发现 #3 —— 字幕被跳过时必须能被调用方看见
# ----------------------------------------------------------------------


@requires_ffmpeg
def test_finalize_reports_subtitles_skipped_for_zero_duration_segment(tmp_path):
    """损坏分镜 -> collect_render_segments 用 0.0 兜底 -> 整轨被丢弃。
    当前 finalize 只返回一个路径字符串，调用方无从分辨这部片子有没有字幕。"""
    concat = _make_video(str(tmp_path / "video" / "concat.mp4"), with_audio=True)
    script = _script([_frame("f1", "第一句"), _frame("f2", "第二句")])

    res = RenderEngine(output_dir=str(tmp_path)).finalize(
        script, concat, ffmpeg_path=FF, segments=[_seg("f1", 2.0), _seg("f2", 0.0)]
    )
    assert res.path is not None  # 音频链照样生效
    assert res.subtitles_burned is False
    assert "duration" in (res.skip_reason or "")


@requires_ffmpeg
def test_burn_failure_does_not_take_bgm_and_loudnorm_down_with_it(tmp_path, monkeypatch):
    """终审发现 #3：烧录与音频混音共用同一次 ffmpeg 调用，所以字幕失败会连坐
    掉 BGM 和响度归一。字幕失败时必须降级重试一次不带烧录的 pass 2。"""
    import src.apps.comic_gen.editing as editing

    concat = _make_video(str(tmp_path / "video" / "concat.mp4"), with_audio=True)
    bgm = _make_audio(str(tmp_path / "presets" / "bgm.mp3"), seconds=3.0)
    # 让烧录必然失败：指向一个不存在的字幕文件
    monkeypatch.setattr(editing, "escape_filter_path", lambda p: "does_not_exist.ass")

    script = _script([_frame("f1", "第一句台词")])
    res = RenderEngine(output_dir=str(tmp_path)).finalize(
        script, concat, ffmpeg_path=FF, segments=[_seg("f1", 2.0)], bgm_abs_path=bgm
    )
    assert res.path is not None, "字幕失败把整个 pass 2 拖垮了"
    assert res.subtitles_burned is False
    assert res.skip_reason == "burn_failed"
    assert res.bgm_applied is True
    assert res.loudnorm_applied is True


@requires_ffmpeg
def test_finalize_reports_subtitles_disabled(tmp_path):
    concat = _make_video(str(tmp_path / "video" / "concat.mp4"), with_audio=True)
    script = _script([_frame("f1", "第一句")], subtitles=False)
    res = RenderEngine(output_dir=str(tmp_path)).finalize(
        script, concat, ffmpeg_path=FF, segments=[_seg("f1", 2.0)]
    )
    assert res.subtitles_burned is False
    assert res.skip_reason == "disabled"


@requires_ffmpeg
def test_finalize_reports_no_dialogue(tmp_path):
    concat = _make_video(str(tmp_path / "video" / "concat.mp4"), with_audio=True)
    script = _script([_frame("f1")])  # 无台词
    res = RenderEngine(output_dir=str(tmp_path)).finalize(
        script, concat, ffmpeg_path=FF, segments=[_seg("f1", 2.0)]
    )
    assert res.subtitles_burned is False
    assert res.skip_reason == "no_dialogue"
