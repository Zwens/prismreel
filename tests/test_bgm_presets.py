import os
import re
import sys

import pytest

from src.apps.comic_gen.audio import (
    BGM_PRESETS,
    get_bgm_presets,
    install_bundled_bgm_presets,
    verify_bgm_assets,
)

BGM_DIR = os.path.join("output", "presets", "bgm")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


# ----------------------------------------------------------------------
# Packaging: the desktop build (终审阻塞项 6)
# ----------------------------------------------------------------------
#
# main.py chdir()s to ~/.prismreel before importing the app, and every BGM
# lookup is CWD-relative (audio._bgm_abs_path -> os.path.join("output", url),
# pipeline -> safe_resolve_path("output", ...)). PyInstaller unpacks bundled
# data under sys._MEIPASS instead. So shipping the mp3s via --add-data alone
# puts them somewhere the app never looks: every packaged export comes out
# with no background music — the exact bug this branch exists to fix.


def _fake_bundle(tmp_path, monkeypatch, *, files=None):
    """Stand in for a PyInstaller bundle: _MEIPASS + a ~/.prismreel-style cwd."""
    meipass = tmp_path / "_MEI12345"
    bundled = meipass / "output" / "presets" / "bgm"
    bundled.mkdir(parents=True)
    for name in files if files is not None else [os.path.basename(p["url"]) for p in BGM_PRESETS]:
        (bundled / name).write_bytes(b"ID3fake-mp3-bytes")
    (bundled / "LICENSES.md").write_text("placeholder", encoding="utf-8")

    workdir = tmp_path / "prismreel_home"
    workdir.mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.chdir(workdir)
    return meipass, workdir


def test_bundled_presets_are_installed_into_the_working_output_dir(tmp_path, monkeypatch):
    """The packaged app must end up with playable mp3s where it looks for them."""
    _fake_bundle(tmp_path, monkeypatch)

    # Precondition: bundling alone leaves every preset unreachable.
    assert verify_bgm_assets() == [p["url"] for p in BGM_PRESETS]

    installed = install_bundled_bgm_presets()

    assert sorted(installed) == sorted(p["url"] for p in BGM_PRESETS)
    assert verify_bgm_assets() == [], "presets still unreachable after install"
    assert os.path.exists(
        os.path.join(BGM_DIR, "LICENSES.md")
    ), "licences must travel with the audio"


def test_install_does_not_overwrite_user_replaced_audio(tmp_path, monkeypatch):
    """A user who dropped in real licensed music must not get it clobbered."""
    _fake_bundle(tmp_path, monkeypatch)
    os.makedirs(BGM_DIR, exist_ok=True)
    mine = os.path.join(BGM_DIR, os.path.basename(BGM_PRESETS[0]["url"]))
    with open(mine, "wb") as f:
        f.write(b"my-own-licensed-track")

    installed = install_bundled_bgm_presets()

    assert BGM_PRESETS[0]["url"] not in installed
    with open(mine, "rb") as f:
        assert f.read() == b"my-own-licensed-track"


def test_install_is_a_noop_when_not_frozen(tmp_path, monkeypatch):
    """Dev runs have the real files in the repo; nothing to install, no crash."""
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.chdir(tmp_path)
    assert install_bundled_bgm_presets() == []


def test_install_tolerates_an_incomplete_bundle(tmp_path, monkeypatch):
    """A partially-shipped bundle installs what it has instead of raising."""
    only = os.path.basename(BGM_PRESETS[0]["url"])
    _fake_bundle(tmp_path, monkeypatch, files=[only])
    assert install_bundled_bgm_presets() == [BGM_PRESETS[0]["url"]]


# ----------------------------------------------------------------------
# Drift guard: build.spec.template was updated, the shipping build scripts
# were not. The template is not what actually builds the app — both
# build_windows.ps1 and build_mac.sh delete *.spec and pass --add-data on
# the command line — so the un-ignore work landed in a file the release
# never reads.
# ----------------------------------------------------------------------

BUILD_FILES = {
    "build_windows.ps1": r'"--add-data",\s*"output/presets;output/presets"',
    "build_mac.sh": r'--add-data\s+"output/presets:output/presets"',
    "build.spec.template": r"\('output/presets/bgm',\s*'output/presets/bgm'\)",
}


@pytest.mark.parametrize("filename,pattern", sorted(BUILD_FILES.items()))
def test_build_definitions_ship_the_bgm_presets(filename, pattern):
    with open(os.path.join(REPO_ROOT, filename), encoding="utf-8") as f:
        content = f.read()
    assert re.search(pattern, content), (
        f"{filename} does not ship output/presets — the packaged app would have "
        f"no BGM mp3s and every export would be silent again."
    )


CONFIG_FILES = {
    "build_windows.ps1": r'"--add-data",\s*"config;config"',
    "build_mac.sh": r'--add-data\s+"config:config"',
    "build.spec.template": r"\('config',\s*'config'\)",
    "Dockerfile.backend": r"COPY\s+config/\s+config/",
}


@pytest.mark.parametrize("filename,pattern", sorted(CONFIG_FILES.items()))
def test_build_definitions_ship_the_model_catalog(filename, pattern):
    """models.py reads config/model_catalog/*.yaml at import time.

    Found by actually building a bundle: without this entry the packaged
    binary dies with FileNotFoundError on catalog.meta.yaml before the
    window is ever created.
    """
    with open(os.path.join(REPO_ROOT, filename), encoding="utf-8") as f:
        content = f.read()
    assert re.search(pattern, content), (
        f"{filename} does not ship config/ — the packaged app crashes at import "
        f"(model_catalog reads catalog.meta.yaml before the UI starts)."
    )
