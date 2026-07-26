import os

from src.apps.comic_gen.audio import BGM_PRESETS, get_bgm_presets, verify_bgm_assets

BGM_DIR = os.path.join("output", "presets", "bgm")


def test_all_presets_have_files():
    """回归：8 个预设的 catalog 存在但音频文件缺失，导致导出静音。"""
    missing = verify_bgm_assets()
    assert missing == [], (
        f"缺少 BGM 音频文件: {missing}. "
        f"请放置到 {BGM_DIR}/ —— 缺失会导致 _maybe_apply_bgm_mux 静默跳过，成片没有背景音乐。"
    )


def test_licenses_documented():
    assert os.path.exists(
        os.path.join(BGM_DIR, "LICENSES.md")
    ), "BGM 素材必须附 LICENSES.md 记录来源与许可证"


def test_placeholder_status_is_visible():
    """占位音频不可对外发布 —— LICENSES.md 必须把这件事说清楚。

    这条测试是故意留下的提醒：等真实素材替换完、表里不再有「占位」，
    它自然就变成对「授权已登记」的断言。
    """
    with open(os.path.join(BGM_DIR, "LICENSES.md"), encoding="utf-8") as f:
        content = f.read()
    if "占位" in content:
        assert "不可对外发布" in content, "LICENSES.md 中仍有占位音频，必须显著标注不可对外发布"


def test_presets_expose_availability():
    presets = get_bgm_presets()
    assert len(presets) == len(BGM_PRESETS)
    for p in presets:
        assert "available" in p
        assert isinstance(p["available"], bool)
