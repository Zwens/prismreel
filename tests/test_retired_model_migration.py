"""已下架模型 id 的迁移映射。

DashScope 拔除后，wan / qwen-image / happyhorse / pixverse 四个家族整体消失。
存量 6 个项目里有 28 处模型引用指向它们，直接打开会拿到一个目录里不存在的
模型 id —— 生成时才失败，而且用户无从知道该换成什么。

映射规则有两条不能违反：

1. **模态必须一致**。图生视频映射成文生图会静默产出完全不同的东西。v2v
   （视频编辑）能保住是因为实测发现 Seedance 支持 VideoEditing，目录漏标了。
2. **未知 id 不静默替换**。猜一个再悄悄换掉，比明确告诉用户「该模型已下架」
   更糟 —— 用户会以为还是原来的模型在跑。
"""

import pytest

from src.utils.retired_models import (
    RETIRED_MODEL_MAP,
    migrate_model_id,
    migrate_project_models,
)


# 四个待删家族在删除前的完整 id 清单（含容器 id 与 legacy_id），
# 逐条来自 config/model_catalog/families/*.yaml。
RETIRED_IDS = [
    # wan — 图像
    "wan2.7-image-pro", "wan2.7-image", "wan2.6-t2i", "wan2.6-image",
    "wan2.5-t2i-preview", "wan2.5-i2i-preview", "wan2.2-t2i-plus", "wan2.2-t2i-flash",
    # wan — 视频
    "wan2.7-i2v", "wan2.7-r2v", "wan2.7-t2v", "wan2.7-videoedit",
    "wan2.6-i2v", "wan2.6-r2v", "wan2.6-i2v-flash", "wan2.5-i2v-preview",
    "wan2.2-i2v-plus", "wan2.2-i2v-flash",
    # qwen
    "qwen-image-2.0-pro", "qwen-image-2.0",
    # happyhorse
    "happyhorse-1.0-i2v", "happyhorse-1.0-r2v", "happyhorse-1.0-t2v",
    "happyhorse-1.0-video-edit",
    # pixverse
    "pixverse-c1-i2v", "pixverse-c1-r2v", "pixverse-v5.6-r2v", "pixverse-v4-i2v",
    # 容器 id
    "wan/wan2.7-video", "wan/wan2.6-video",
    "happyhorse/happyhorse-1.0-video",
    "pixverse/pixverse-v6-video", "pixverse/pixverse-c1-video",
]

IMAGE_IDS = {
    "wan2.7-image-pro", "wan2.7-image", "wan2.6-t2i", "wan2.6-image",
    "wan2.5-t2i-preview", "wan2.5-i2i-preview", "wan2.2-t2i-plus",
    "wan2.2-t2i-flash", "qwen-image-2.0-pro", "qwen-image-2.0",
}
VIDEO_EDIT_IDS = {"wan2.7-videoedit", "happyhorse-1.0-video-edit"}


class TestCoverage:
    def test_every_retired_id_has_a_replacement(self):
        missing = [i for i in RETIRED_IDS if i not in RETIRED_MODEL_MAP]
        assert not missing, f"漏映射会让存量项目打开即失效: {missing}"

    def test_no_stale_entries(self):
        # 映射表里出现一个仍然在售的 id，说明表写错了。
        extra = [k for k in RETIRED_MODEL_MAP if k not in RETIRED_IDS]
        assert not extra, f"映射表包含未下架的 id: {extra}"


class TestModalityPreserved:
    def test_image_models_map_to_image_models(self):
        for old in IMAGE_IDS:
            new = migrate_model_id(old)
            assert new.startswith("gemini-") and new.endswith("-image"), \
                f"{old} 映射到了非图像模型 {new}"

    def test_video_models_map_to_seedance_video(self):
        for old in RETIRED_IDS:
            if old in IMAGE_IDS:
                continue
            new = migrate_model_id(old)
            assert new.startswith("seedance-"), f"{old} 映射到了非视频模型 {new}"

    def test_video_edit_keeps_the_v2v_modality(self):
        # 实测 Seedance 全系支持 VideoEditing，目录此前漏标；把视频编辑降级成
        # 图生视频会产出完全不同的东西。
        for old in VIDEO_EDIT_IDS:
            assert migrate_model_id(old) == "seedance-2.5-v2v"

    def test_i2v_stays_i2v_and_r2v_stays_r2v(self):
        assert migrate_model_id("happyhorse-1.0-i2v").endswith("-i2v")
        assert migrate_model_id("happyhorse-1.0-r2v").endswith("-r2v")
        assert migrate_model_id("wan2.7-t2v").endswith("-t2v")

    def test_pro_tier_maps_to_pro_tier(self):
        # 存量项目里 18 处引用的正是 wan2.7-image-pro；降到 flash 档会掉画质。
        assert migrate_model_id("wan2.7-image-pro") == "gemini-3-pro-image"
        assert migrate_model_id("qwen-image-2.0-pro") == "gemini-3-pro-image"

    def test_fast_tier_maps_to_fast_tier(self):
        assert migrate_model_id("wan2.6-i2v-flash") == "seedance-2.0-fast-i2v"
        assert migrate_model_id("wan2.2-i2v-flash") == "seedance-2.0-fast-i2v"


class TestUnknownIds:
    @pytest.mark.parametrize("live", [
        "gemini-3.1-flash-image", "seedance-2.5-i2v", "kling-v3-i2v", "viduq3-pro-i2v",
    ])
    def test_live_ids_pass_through_untouched(self, live):
        assert migrate_model_id(live) == live

    def test_unknown_id_is_returned_as_is(self):
        # 猜一个替代再静默换掉，比让 UI 标出「已下架」更糟。
        assert migrate_model_id("some-model-we-never-heard-of") == "some-model-we-never-heard-of"

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_values_survive(self, empty):
        assert migrate_model_id(empty) == empty


class TestProjectRewrite:
    def test_rewrites_every_model_field_it_finds(self):
        project = {
            "id": "p1",
            "model_settings": {
                "t2i_model": "wan2.7-image-pro",
                "i2v_model": "happyhorse-1.0-i2v",
            },
            "frames": [
                {"id": "f1", "image_model": "wan2.6-image", "video_model": "happyhorse-1.0-r2v"},
                {"id": "f2", "image_model": "gemini-3.1-flash-image"},
            ],
        }
        migrated, changed = migrate_project_models(project)

        assert changed is True
        assert migrated["model_settings"]["t2i_model"] == "gemini-3-pro-image"
        assert migrated["model_settings"]["i2v_model"] == "seedance-2.5-i2v"
        assert migrated["frames"][0]["image_model"] == "gemini-3.1-flash-image"
        assert migrated["frames"][0]["video_model"] == "seedance-2.5-r2v"

    def test_reports_no_change_when_nothing_is_retired(self):
        # 回写落盘要靠这个信号；每次读取都改写会把所有项目的 mtime 刷掉。
        project = {"frames": [{"image_model": "gemini-3.1-flash-image"}]}
        _, changed = migrate_project_models(project)
        assert changed is False

    def test_leaves_non_model_fields_alone(self):
        project = {
            "title": "wan2.7-image-pro",          # 标题恰好同名，不该被改
            "notes": "用 happyhorse-1.0-i2v 试过",  # 自由文本，不该被改
            "frames": [{"image_model": "wan2.7-image-pro"}],
        }
        migrated, _ = migrate_project_models(project)

        assert migrated["title"] == "wan2.7-image-pro"
        assert "happyhorse-1.0-i2v" in migrated["notes"]
        assert migrated["frames"][0]["image_model"] == "gemini-3-pro-image"

    def test_handles_deeply_nested_structures(self):
        project = {"series": {"episodes": [{"shots": [{"video_model": "pixverse-c1-i2v"}]}]}}
        migrated, changed = migrate_project_models(project)
        assert changed is True
        assert migrated["series"]["episodes"][0]["shots"][0]["video_model"] == "seedance-2.5-i2v"

    def test_does_not_mutate_the_input(self):
        # 改写失败时原始数据必须完好，否则一次异常就毁掉项目文件。
        project = {"frames": [{"image_model": "wan2.7-image-pro"}]}
        migrate_project_models(project)
        assert project["frames"][0]["image_model"] == "wan2.7-image-pro"

    def test_empty_project_is_safe(self):
        assert migrate_project_models({}) == ({}, False)
