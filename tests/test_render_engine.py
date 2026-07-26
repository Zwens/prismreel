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
        _script_with([f], [t]), resolve=lambda u: f"/abs/{u}", probe=lambda p: 3.0
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
        _script_with([f1, f2], tasks), resolve=lambda u: f"/abs/{u}", probe=lambda p: 2.0
    )
    assert [s.video_path for s in segs] == ["/abs/video/a.mp4", "/abs/video/b.mp4"]


def test_frames_without_any_video_are_dropped():
    segs = collect_render_segments(
        _script_with([_frame("f1")], []), resolve=lambda u: f"/abs/{u}", probe=lambda p: 2.0
    )
    assert segs == []


def test_segments_carry_measured_duration():
    f = _frame("f1", dubbed_video_url="video/a.mp4")
    segs = collect_render_segments(
        _script_with([f], []), resolve=lambda u: f"/abs/{u}", probe=lambda p: 4.25
    )
    assert segs[0].duration_s == pytest.approx(4.25)


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
