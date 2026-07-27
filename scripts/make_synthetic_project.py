"""Build a synthetic V-1 baseline project and drive it through the REAL render chain.

Task 10 scope decision (2026-07-27): this machine has no output/projects.json
and no real project, and running the real generation pipeline would spend
real DashScope/Kling/Vidu credit. V-1 only changed the render/subtitle/audio
layer, not generation, so this script builds a synthetic project — ffmpeg
placeholder shot videos + real Chinese dialogue + real TTS — and then calls
the genuine `ComicGenPipeline.merge_videos()` so every line V-1 actually
wrote (collect_render_segments -> concat -> RenderEngine.finalize -> audio
chain -> subtitle burn) runs for real.

Six shots are deliberately chosen to hit every invariant fixed during V-1
(see the docstring table below and the SHOTS list).

Usage:
    python scripts/make_synthetic_project.py [--skip-tts]

Prints script_id / series_id / merged_video_url and writes a JSON summary to
output/verify/synthetic_run_summary.json for the report to reference.
"""

import argparse
import json
import os
import subprocess
import sys
import uuid
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.apps.comic_gen.models import Character, Scene, StoryboardFrame, VideoTask  # noqa: E402
from src.apps.comic_gen.pipeline import ComicGenPipeline  # noqa: E402
from src.utils.system_check import get_ffmpeg_path  # noqa: E402

WIDTH, HEIGHT = 1080, 1920
FPS = 25
VOICE_ID = "longxiaochun_v2"
FONT_FILE = "C\\:/Windows/Fonts/arial.ttf"

# (shot_no, duration_s, dialogue-or-None, dub_offset_ms, purpose)
# Durations sum to 21.6s — matches the brief's expected merged-video length.
SHOTS: List[Tuple[int, float, Optional[str], int, str]] = [
    (1, 4.0, "你到底想说什么？", 0, "基础 cue"),
    (
        2,
        5.0,
        "这条街从我们小时候起就没怎么变过，青石板路、老槐树，还有巷口那家永远飘着"
        "葱油饼香气的小铺子，如今全都还安静地留在原地等着我们回来看一眼。",
        0,
        "超长句（60+ 字），触发 wrap_cjk 折行与截断",
    ),
    (3, 3.0, None, 0, "无台词 — 验证时钟仍推进（Task 5 核心不变量）"),
    (
        4,
        4.0,
        "你先在这里等一下，我去看看外面的情况到底怎么样。\n千万不要出声，知道吗。",
        0,
        "含手打换行的两行台词 — 有 \\N 仍要折行",
    ),
    (5, 0.6, "快跑！", 0, "时长 < MIN_CUE_S(0.8s) — 验证不越界重叠"),
    (6, 5.0, "这一切，终于要结束了。", 800, "dub_offset_ms=800 — 验证偏移"),
]

_COLORS = ["navy", "maroon", "darkgreen", "purple", "olive", "teal"]


def _run(cmd: List[str], timeout: int = 60) -> None:
    result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"{result.stderr.decode(errors='replace')[-2000:]}"
        )


def make_shot_video(
    ffmpeg: str,
    shot_no: int,
    duration_s: float,
    out_path: str,
    tts_path: Optional[str],
    dub_offset_ms: int,
) -> None:
    """Placeholder shot video: solid color + burned-in shot number.

    When TTS audio exists it is muxed in as the shot's OWN dialogue track
    (delayed by dub_offset_ms, matching what pipeline.preview_dub's real
    adelay does) — this is what `[0:a]` means to audio_mixer.build_audio_filter
    downstream, since the audio chain reads the concatenated video's own
    audio, not frame.audio_url directly.
    """
    color = _COLORS[(shot_no - 1) % len(_COLORS)]
    drawtext = (
        f"drawtext=fontfile='{FONT_FILE}':text='SHOT {shot_no}':fontcolor=white:"
        "fontsize=110:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.45:boxborderw=24"
    )
    color_src = f"color=c={color}:s={WIDTH}x{HEIGHT}:d={duration_s}:r={FPS}"

    if tts_path and os.path.exists(tts_path):
        delay = f"{dub_offset_ms}|{dub_offset_ms}"
        filter_complex = f"[0:v]{drawtext}[v];[1:a]adelay={delay},apad[a]"
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            color_src,
            "-i",
            tts_path,
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{duration_s}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            out_path,
        ]
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            color_src,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-vf",
            drawtext,
            "-t",
            f"{duration_s}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-shortest",
            out_path,
        ]
    _run(cmd, timeout=60)


def build_script(pipeline: ComicGenPipeline):
    """Create the project via the real create_project() path, then attach
    a synthetic character/scene/frames directly — the fixture data itself
    isn't part of the V-1 code path under test, only what consumes it is."""
    script = pipeline.create_project(
        "V-1 基线验证合成短剧",
        "（合成项目，仅用于 Task 10 端到端验证；无真实剧本文本，全部台词均手写。）",
        skip_analysis=True,
    )

    scene = Scene(
        id=f"scene_{uuid.uuid4().hex[:8]}", name="旧巷", description="狭窄石板巷，黄昏微光。"
    )
    character = Character(
        id=f"char_{uuid.uuid4().hex[:8]}",
        name="林墨",
        description="青年侦探，冷静敏锐。",
        voice_id=VOICE_ID,
        voice_name="龙小淳 (知性女)",
    )

    frames = []
    for shot_no, duration_s, dialogue, dub_offset_ms, _purpose in SHOTS:
        frames.append(
            StoryboardFrame(
                id=f"frame_{shot_no}_{uuid.uuid4().hex[:6]}",
                scene_id=scene.id,
                character_ids=[character.id] if dialogue else [],
                action_description=f"分镜 {shot_no} 占位动作描述。",
                dialogue=dialogue,
                speaker=character.name if dialogue else None,
                duration=max(1, round(duration_s)),
                dub_offset_ms=dub_offset_ms,
            )
        )

    script.characters = [character]
    script.scenes = [scene]
    script.frames = frames
    script.bgm_url = "presets/bgm/calm_warm.mp3"
    pipeline._save_data()
    return script


def generate_tts_for_frame(
    pipeline: ComicGenPipeline, frame: StoryboardFrame, character: Character
) -> Tuple[Optional[str], str]:
    """Try real DashScope/CosyVoice TTS; never raise — a failure must
    degrade to the reading-rate estimate branch (build_subtitle_cues'
    fallback), not abort the synthetic run. Returns (abs_audio_path, note).
    """
    try:
        pipeline.audio_generator.generate_dialogue(
            frame, character, speed=1.0, pitch=1.0, volume=50
        )
    except Exception as exc:  # pragma: no cover - defensive, see docstring
        frame.audio_url = None
        frame.audio_error = str(exc)
        return None, f"TTS raised: {exc}"

    if not frame.audio_url:
        return None, frame.audio_error or "TTS returned no audio_url"

    abs_path = os.path.join("output", frame.audio_url)
    if not os.path.exists(abs_path):
        return None, f"audio_url set but file missing: {abs_path}"
    return abs_path, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-tts",
        action="store_true",
        help="Force the reading-rate estimate path (skip DashScope TTS calls entirely).",
    )
    args = parser.parse_args()

    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        print("ffmpeg not found on PATH; aborting.", file=sys.stderr)
        return 1

    pipeline = ComicGenPipeline()
    script = build_script(pipeline)
    character = script.characters[0]

    shot_dir = os.path.join("output", "video_inputs", "synthetic_baseline")
    os.makedirs(shot_dir, exist_ok=True)

    tts_notes = {}
    for (shot_no, duration_s, dialogue, dub_offset_ms, purpose), frame in zip(SHOTS, script.frames):
        tts_path = None
        if dialogue and not args.skip_tts:
            tts_path, note = generate_tts_for_frame(pipeline, frame, character)
            tts_notes[shot_no] = note
        elif dialogue:
            tts_notes[shot_no] = "skipped by --skip-tts (estimate path)"
        else:
            tts_notes[shot_no] = "no dialogue"

        out_path = os.path.join(shot_dir, f"shot_{shot_no}.mp4")
        make_shot_video(ffmpeg, shot_no, duration_s, out_path, tts_path, dub_offset_ms)

        rel_video_url = os.path.relpath(out_path, "output").replace(os.sep, "/")
        task = VideoTask(
            id=f"task_{shot_no}_{uuid.uuid4().hex[:6]}",
            project_id=script.id,
            frame_id=frame.id,
            image_url="synthetic://placeholder",
            prompt=f"synthetic placeholder shot {shot_no}",
            status="completed",
            video_url=rel_video_url,
            duration=max(1, round(duration_s)),
        )
        script.video_tasks.append(task)
        print(
            f"[shot {shot_no}] {purpose} | duration={duration_s}s "
            f"dialogue={'yes' if dialogue else 'no'} tts={tts_notes[shot_no]} -> {rel_video_url}"
        )

    pipeline._save_data()

    # Wrap as a 1-episode Series (real create_series/add_episode_to_series
    # path) so scripts/baseline_report.py has a series_id to group by.
    series = pipeline.create_series("V-1 基线验证系列")
    pipeline.add_episode_to_series(series.id, script.id, episode_number=1)

    print(f"\nscript_id={script.id}")
    print(f"series_id={series.id}")

    print("\nCalling the REAL pipeline.merge_videos() ...")
    merged_script = pipeline.merge_videos(script.id)
    print(f"merged_video_url={merged_script.merged_video_url}")

    summary = {
        "script_id": script.id,
        "series_id": series.id,
        "merged_video_url": merged_script.merged_video_url,
        "tts_notes": tts_notes,
        "shots": [
            {
                "shot_no": s[0],
                "duration_s": s[1],
                "dialogue": s[2],
                "dub_offset_ms": s[3],
                "purpose": s[4],
            }
            for s in SHOTS
        ],
    }
    summary_path = os.path.join("output", "verify", "synthetic_run_summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nSummary written to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
