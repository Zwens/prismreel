import os
import subprocess

import pytest

from src.apps.comic_gen.editing import collect_render_segments, escape_filter_path
from src.apps.comic_gen.models import Script, StoryboardFrame, VideoTask
from src.utils.system_check import get_ffmpeg_path

requires_ffmpeg = pytest.mark.skipif(not get_ffmpeg_path(), reason="ffmpeg not installed")


def test_escape_path_windows_drive():
    assert escape_filter_path(r"C:\out\sub.ass") == "C\\:/out/sub.ass"


def test_escape_path_posix():
    assert escape_filter_path("/out/sub.ass") == "/out/sub.ass"


def _script_with(frames, tasks):
    return Script(
        id="s1",
        title="t",
        original_text="x",
        frames=frames,
        video_tasks=tasks,
        created_at=0.0,
        updated_at=0.0,
    )


# StoryboardFrame requires scene_id; VideoTask requires image_url + prompt
# (models.py:353-354, :171-176). Helpers keep the noise out of the tests.
def _frame(fid, **kw):
    return StoryboardFrame(id=fid, scene_id="sc1", **kw)


def _task(tid, frame_id, video_url):
    return VideoTask(
        id=tid,
        project_id="s1",
        frame_id=frame_id,
        image_url="",
        prompt="",
        status="completed",
        video_url=video_url,
    )


def test_prefers_dubbed_video():
    """回归 merge_videos 的选片优先级：配音版 > 选中版 > 首个完成版。"""
    f = _frame("f1", dubbed_video_url="video/dub.mp4")
    f.selected_video_id = "t1"
    t = _task("t1", "f1", "video/sel.mp4")
    segs = collect_render_segments(
        _script_with([f], [t]),
        resolve=lambda u: f"/abs/{u}",
        probe=lambda p: 3.0,
        exists=lambda p: True,
    )
    assert len(segs) == 1
    assert segs[0].video_path == "/abs/video/dub.mp4"
    assert segs[0].frame_id == "f1"


def test_falls_back_to_selected_then_first_completed():
    f1 = _frame("f1")
    f1.selected_video_id = "t1"
    f2 = _frame("f2")  # 无 selected
    tasks = [_task("t1", "f1", "video/a.mp4"), _task("t2", "f2", "video/b.mp4")]
    segs = collect_render_segments(
        _script_with([f1, f2], tasks),
        resolve=lambda u: f"/abs/{u}",
        probe=lambda p: 2.0,
        exists=lambda p: True,
    )
    assert [s.video_path for s in segs] == ["/abs/video/a.mp4", "/abs/video/b.mp4"]


def test_frames_without_any_video_are_dropped():
    segs = collect_render_segments(
        _script_with([_frame("f1")], []),
        resolve=lambda u: f"/abs/{u}",
        probe=lambda p: 2.0,
        exists=lambda p: True,
    )
    assert segs == []


def test_segments_carry_measured_duration():
    f = _frame("f1", dubbed_video_url="video/a.mp4")
    segs = collect_render_segments(
        _script_with([f], []),
        resolve=lambda u: f"/abs/{u}",
        probe=lambda p: 4.25,
        exists=lambda p: True,
    )
    assert segs[0].duration_s == pytest.approx(4.25)


def test_dubbed_video_missing_falls_back_to_take():
    """回归发现 (1)：dubbed_video_url 指向的文件在磁盘上不存在时，必须
    像 merge_videos 一样退回到 take，而不是继续用那条不存在的路径
    （否则 probe 会失败 -> duration=0.0 -> 字幕被整集禁用）。"""
    f = _frame("f1", dubbed_video_url="video/dub.mp4")
    t = _task("t1", "f1", "video/take.mp4")
    segs = collect_render_segments(
        _script_with([f], [t]),
        resolve=lambda u: f"/abs/{u}",
        probe=lambda p: 2.0,
        exists=lambda p: p != "/abs/video/dub.mp4",
    )
    assert len(segs) == 1
    assert segs[0].video_path == "/abs/video/take.mp4"


def test_dangling_selected_video_id_is_skipped_not_substituted():
    """回归发现 (2)：selected_video_id 指向不存在的 task 时，merge_videos
    直接跳过该镜头；collect_render_segments 必须一致，不能替换成别的
    take —— 否则字幕时间线比实际拼接的视频多出一镜，后续全部字幕错位。"""
    f = _frame("f1")
    f.selected_video_id = "does-not-exist"
    other_task = _task("t2", "f1", "video/other.mp4")
    segs = collect_render_segments(
        _script_with([f], [other_task]),
        resolve=lambda u: f"/abs/{u}",
        probe=lambda p: 2.0,
        exists=lambda p: True,
    )
    assert segs == []


def test_bad_video_url_is_skipped_not_raised():
    """回归发现 C：video_url / dubbed_video_url 逃出 output 目录（脏数据/
    被篡改的项目文件）时，resolve() 必须只丢弃/退化这一镜，不能让整个
    collect_render_segments 抛出 —— merge_videos 在 pass 1 之前、任何
    try/except 之外调用它，一次未捕获的 raise 会让整段导出失败。两个
    resolve() 调用点都要覆盖：dubbed 分支（应退回到 take）和已选 take
    分支（应跳过该镜）。用真实的 _safe_resolve_path 绑定到 "output"，
    才能触发真正的 ValueError。"""
    from src.apps.comic_gen.pipeline import _safe_resolve_path

    # dubbed_video_url escapes the base dir but a valid take exists ->
    # must fall back to the take, not raise.
    dubbed_bad = _frame("f1", dubbed_video_url="../../../../etc/passwd")
    dubbed_fallback_task = _task("t1", "f1", "video/f1_take.mp4")

    # selected_video_id resolves to a task whose video_url escapes the
    # base dir, with no fallback -> must be skipped, not raise.
    selected_bad = _frame("f2")
    selected_bad.selected_video_id = "t2"
    selected_bad_task = _task("t2", "f2", "../../../../etc/passwd")

    # A normal frame, to prove the render continues past both bad ones.
    good = _frame("f3")
    good.selected_video_id = "t3"
    good_task = _task("t3", "f3", "video/f3.mp4")

    segs = collect_render_segments(
        _script_with(
            [dubbed_bad, selected_bad, good],
            [dubbed_fallback_task, selected_bad_task, good_task],
        ),
        resolve=lambda u: _safe_resolve_path("output", u),
        probe=lambda p: 2.0,
    )
    assert [s.frame_id for s in segs] == ["f1", "f3"]


@requires_ffmpeg
def test_ass_burn_accepted_by_ffmpeg(tmp_path):
    """真跑一次烧录 —— 路径转义写错在单测里看不出来。"""
    from src.apps.comic_gen.editing import escape_filter_path
    from src.apps.comic_gen.subtitle import SUBTITLE_TEMPLATES, SubtitleCue, render_ass

    ff = get_ffmpeg_path()
    ass_path = tmp_path / "s.ass"
    ass_path.write_text(
        render_ass(
            [SubtitleCue(start_s=0.0, end_s=1.5, text="测试字幕")],
            SUBTITLE_TEMPLATES["douyin"],
            play_res=(320, 240),
        ),
        encoding="utf-8",
    )
    out = str(tmp_path / "burned.mp4")
    subprocess.run(
        [
            ff,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x240:rate=25",
            "-vf",
            f"ass='{escape_filter_path(str(ass_path))}'",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-t",
            "2",
            out,
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    assert os.path.exists(out)
