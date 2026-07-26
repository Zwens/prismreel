from src.apps.comic_gen.subtitle import (
    SUBTITLE_TEMPLATES,
    SubtitleCue,
    render_ass,
    wrap_cjk,
)


def test_two_templates_exist():
    assert set(SUBTITLE_TEMPLATES) == {"douyin", "cinematic"}


def test_douyin_avoids_platform_ui():
    assert SUBTITLE_TEMPLATES["douyin"].margin_v >= 150


def test_wrap_short_text_unchanged():
    assert wrap_cjk("短句", 18, 2) == "短句"


def test_wrap_inserts_ass_newline():
    text = "一" * 25
    out = wrap_cjk(text, 18, 2)
    assert out == "一" * 18 + r"\N" + "一" * 7


def test_wrap_truncates_beyond_max_lines():
    text = "一" * 60
    out = wrap_cjk(text, 18, 2)
    assert out.count(r"\N") == 1
    assert out.endswith("…")


def test_ass_has_required_sections():
    ass = render_ass([], SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert "[Script Info]" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass


def test_color_conversion_is_bgr_with_alpha():
    """ASS 用 &HAABBGGRR —— 写成 RGB 会让红蓝对调。"""
    style = SUBTITLE_TEMPLATES["douyin"].model_copy(
        update={"primary_color": "#FF0000", "outline_color": "#00FF00"}
    )
    ass = render_ass([], style, play_res=(1080, 1920))
    assert "&H000000FF" in ass  # 红 RGB=FF0000 → BGR=0000FF
    assert "&H0000FF00" in ass  # 绿 RGB=00FF00 → BGR=00FF00


def test_timecode_format_is_centiseconds():
    cues = [SubtitleCue(start_s=0.0, end_s=3.456, text="你好")]
    ass = render_ass(cues, SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert "0:00:00.00,0:00:03.45" in ass


def test_timecode_handles_hours():
    cues = [SubtitleCue(start_s=3723.5, end_s=3725.0, text="很久以后")]
    ass = render_ass(cues, SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert "1:02:03.50,1:02:05.00" in ass


def test_dialogue_line_per_cue():
    cues = [
        SubtitleCue(start_s=0.0, end_s=1.0, text="第一句"),
        SubtitleCue(start_s=1.0, end_s=2.0, text="第二句"),
    ]
    ass = render_ass(cues, SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert len([ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]) == 2


def test_braces_are_escaped():
    """ASS 里 {} 是 override tag 定界符，台词里的花括号必须转义。"""
    cues = [SubtitleCue(start_s=0.0, end_s=1.0, text="他说{很好}")]
    ass = render_ass(cues, SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert "{很好}" not in ass
    assert r"\{很好\}" in ass


def test_newlines_in_text_become_ass_breaks():
    cues = [SubtitleCue(start_s=0.0, end_s=1.0, text="第一行\n第二行")]
    ass = render_ass(cues, SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert "\n第二行" not in ass.split("[Events]")[1]
    assert r"第一行\N第二行" in ass


def test_bold_flag_maps_to_minus_one():
    """ASS 里 Bold 是 -1 表示真，0 表示假 —— 写 1 不生效。"""
    ass = render_ass([], SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    style_line = next(ln for ln in ass.splitlines() if ln.startswith("Style:"))
    assert ",-1," in style_line


def test_long_segment_after_authored_break_still_wraps():
    """作者手打了换行、但其中一行很长时，那一行仍必须折行，不能整条跳过换行。"""
    cues = [SubtitleCue(start_s=0.0, end_s=2.0, text="短\n" + "长" * 60)]
    ass = render_ass(cues, SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    body = next(ln for ln in ass.splitlines() if ln.startswith("Dialogue:")).split(",,", 1)[1]
    per_line = SUBTITLE_TEMPLATES["douyin"].chars_per_line
    assert all(len(seg) <= per_line for seg in body.split(r"\N")[1:])


def test_authored_break_does_not_multiply_line_budget():
    """手打换行不得让总行数突破 max_lines。"""
    style = SUBTITLE_TEMPLATES["douyin"]
    out = wrap_cjk("一" * 30 + r"\N" + "二" * 30, style.chars_per_line, style.max_lines)
    assert out.count(r"\N") == style.max_lines - 1


def test_wrap_survives_degenerate_max_lines():
    """max_lines 可被 style_override 覆盖；0 不得让截断分支索引空列表。"""
    assert wrap_cjk("一" * 50, 18, 0)  # 不抛异常
    assert wrap_cjk("一" * 50, 0, 2) == "一" * 50  # per_line<=0 原样返回


def test_style_rejects_out_of_range_values():
    """ge/le 约束把坏值挡在模型层，而不是等到渲染时炸。"""
    import pytest as _pytest
    from pydantic import ValidationError

    from src.apps.comic_gen.models import SubtitleStyle

    for bad in ({"max_lines": 0}, {"chars_per_line": 0}, {"alignment": 0}, {"alignment": 10}):
        with _pytest.raises(ValidationError):
            SubtitleStyle(**bad)
