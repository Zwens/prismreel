import os
import subprocess

import pytest

from src.apps.comic_gen.audio_mixer import build_audio_filter
from src.utils.system_check import get_ffmpeg_path


def test_no_bgm_normalizes_only():
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=False)
    assert "amix" not in f
    assert "sidechaincompress" not in f
    assert "loudnorm=I=-16" in f
    assert f.endswith("[aout]")


def test_no_bgm_without_normalize_is_passthrough_volume():
    f = build_audio_filter(dialogue_level=80, bgm_level=35, has_bgm=False, normalize=False)
    assert "volume=0.800" in f
    assert "loudnorm" not in f
    assert f.endswith("[aout]")


@pytest.mark.parametrize("has_bgm", [False, True])
@pytest.mark.parametrize("ducking", [False, True])
def test_dialogue_label_is_honoured_in_every_branch(has_bgm, ducking):
    """终审发现 #2：拼接产物没有音轨时（默认 Silent Mode），调用方会追加一路
    合成静音输入并把对话标号切过去。三个分支（no-bgm / ducking / 非 ducking）
    里任何一处还写死 [0:a]，pass 2 就会以 "matches no streams" 整体失败。"""
    f = build_audio_filter(
        dialogue_level=100, bgm_level=35, has_bgm=has_bgm, ducking=ducking, dialogue_label="2:a"
    )
    assert "[0:a]" not in f, f
    assert "[2:a]" in f, f


def test_dialogue_label_defaults_to_the_concat_audio():
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=True)
    assert "[0:a]" in f


def test_bgm_with_ducking_splits_dialogue():
    """人声既要进混音又要做侧链 —— 不 asplit 会让 filter graph 报错。"""
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=True)
    assert "asplit=2" in f
    assert "sidechaincompress" in f
    assert "amix=inputs=2" in f
    assert "loudnorm" in f
    assert f.endswith("[aout]")


def test_ducking_sidechain_order():
    """必须是 [bgm][dialogue]sidechaincompress —— 反了就变成人声被BGM压。"""
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=True)
    seg = next(s for s in f.split(";") if "sidechaincompress" in s)
    assert seg.startswith("[bgm_raw][dial_sc]"), seg


def test_ducking_disabled_skips_sidechain():
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=True, ducking=False)
    assert "sidechaincompress" not in f
    assert "amix=inputs=2" in f


def test_bgm_loops():
    """BGM 通常比片子短，必须循环，否则后半段没音乐。"""
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=True)
    assert "aloop=loop=-1" in f


def test_levels_are_clamped():
    f = build_audio_filter(dialogue_level=500, bgm_level=-20, has_bgm=True)
    assert "volume=1.000" in f
    assert "volume=0.000" in f


def test_no_duplicate_labels():
    """同一个标签被定义两次是 filter graph 最常见的错误。

    注：brief 原始实现 `seg[seg.rindex("]", 0, len(seg)):]` 对任何以 "]"
    结尾的片段都只会切出单个字符 "]"（rindex 找到的正是那个结尾字符本身），
    因此对多片段的 filter graph 必然失败，与实现是否正确无关。这里改为从
    片段尾部逐个剥离 "[label]" 分组，以贴合注释所述的原始意图。
    """
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=True)
    produced = []
    for seg in f.split(";"):
        rhs = seg
        while rhs.endswith("]"):
            start = rhs.rindex("[")
            produced.append(rhs[start:])
            rhs = rhs[:start]
    assert len(produced) == len(set(produced)), produced


requires_ffmpeg = pytest.mark.skipif(not get_ffmpeg_path(), reason="ffmpeg not installed")


@requires_ffmpeg
@pytest.mark.parametrize("ducking", [True, False])
def test_graph_accepted_by_ffmpeg(tmp_path, ducking):
    """字符串形状对不代表 ffmpeg 认 —— 真跑一遍。"""
    ff = get_ffmpeg_path()
    out = str(tmp_path / f"mix_{ducking}.wav")
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=True, ducking=ducking)
    subprocess.run(
        [
            ff,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=1",
            "-filter_complex",
            f,
            "-map",
            "[aout]",
            "-t",
            "3",
            out,
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    assert os.path.exists(out)


@requires_ffmpeg
def test_no_bgm_graph_accepted_by_ffmpeg(tmp_path):
    ff = get_ffmpeg_path()
    out = str(tmp_path / "solo.wav")
    f = build_audio_filter(dialogue_level=80, bgm_level=0, has_bgm=False)
    subprocess.run(
        [
            ff,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-filter_complex",
            f,
            "-map",
            "[aout]",
            "-t",
            "3",
            out,
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    assert os.path.exists(out)
