"""风格定调（Art Direction）预设库的结构校验。

style_presets.json 是纯数据驱动的：后端 /art_direction/presets 直接透传，
前端分类 Tab 与筛选完全按 JSON 渲染。没有任何代码会校验它，所以一个手滑的
category 拼写或一条指向不存在图片的 thumbnail 路径都会静默地在 UI 上表现为
「某个预设消失了」或「卡片空了一块」。这些测试就是那道闸门。
"""

import json
import os
from collections import Counter

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESET_FILE = os.path.join(
    REPO_ROOT, "src", "apps", "comic_gen", "style_presets.json"
)
# 缩略图只在 frontend/public 下维护；static/ 是 next build 的产物（已 gitignore），
# 打包时由 build_windows.ps1 的 --add-data static;static 带走。
THUMB_ROOT = os.path.join(REPO_ROOT, "frontend", "public")

REQUIRED_FIELDS = ("name", "name_zh", "positive_prompt", "negative_prompt")


@pytest.fixture(scope="module")
def catalog():
    with open(PRESET_FILE, encoding="utf-8") as f:
        return json.load(f)


def test_parses_as_v2(catalog):
    assert catalog["version"] == 2, "前端按 v2 的 categories + presets 结构渲染"
    assert catalog["categories"], "分类为空会导致风格定调页没有任何 Tab"
    assert catalog["presets"], "预设为空会导致风格定调页无风格可选"


def test_every_preset_has_a_known_category(catalog):
    """回归：改分类 id 或迁移预设时漏改一处，孤儿预设不属于任何 Tab，UI 上直接消失。"""
    known = {c["id"] for c in catalog["categories"]}
    orphans = [
        (p["id"], p["category"])
        for p in catalog["presets"]
        if p.get("category") not in known
    ]
    assert orphans == [], (
        f"预设的 category 不在 categories 中: {orphans}. "
        f"已知分类: {sorted(known)} —— 孤儿预设不会出现在任何分类 Tab 下。"
    )


def test_category_ids_are_unique(catalog):
    dupes = [cid for cid, n in Counter(
        c["id"] for c in catalog["categories"]
    ).items() if n > 1]
    assert dupes == [], f"分类 id 重复: {dupes}"


def test_preset_ids_are_unique(catalog):
    """预设 id 是项目 style_config 的持久化键，重复会让已有项目解析到错的风格。"""
    dupes = [pid for pid, n in Counter(
        p["id"] for p in catalog["presets"]
    ).items() if n > 1]
    assert dupes == [], f"预设 id 重复: {dupes}"


def test_presets_have_required_fields(catalog):
    missing = {
        p.get("id", "<no id>"): [f for f in REQUIRED_FIELDS if not p.get(f)]
        for p in catalog["presets"]
    }
    missing = {k: v for k, v in missing.items() if v}
    assert missing == {}, f"预设缺少必填字段: {missing}"


def test_declared_thumbnails_exist(catalog):
    """回归：JSON 里写了 thumbnail 路径但图没放，卡片会退化成占位图标。

    没声明 thumbnail 是允许的（前端有降级），声明了就必须存在。
    """
    missing = []
    for p in catalog["presets"]:
        thumb = p.get("thumbnail")
        if not thumb:
            continue
        path = os.path.join(THUMB_ROOT, thumb.lstrip("/").replace("/", os.sep))
        if not os.path.isfile(path):
            missing.append((p["id"], thumb))
    assert missing == [], (
        f"缩略图文件缺失: {missing}. "
        f"请放到 frontend/public/assets/styles/ —— static/ 是构建产物，不要手动放那里。"
    )
