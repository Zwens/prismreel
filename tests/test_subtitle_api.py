import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.apps.comic_gen.api import app

    return TestClient(app)


def test_list_templates(client):
    r = client.get("/subtitle/templates")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert ids == {"douyin", "cinematic"}
    for t in r.json():
        assert "font_size" in t and "margin_v" in t


def test_preview_unknown_project_404(client):
    r = client.get("/projects/nope/subtitle/preview")
    assert r.status_code == 404


def test_update_settings_roundtrip(client):
    from src.apps.comic_gen.api import pipeline
    from src.apps.comic_gen.models import Script

    pipeline.scripts["p1"] = Script(
        id="p1", title="t", original_text="x", created_at=0.0, updated_at=0.0
    )

    r = client.put(
        "/projects/p1/subtitle/settings",
        json={"enabled": True, "template_id": "cinematic"},
    )
    assert r.status_code == 200
    assert pipeline.scripts["p1"].subtitle_settings.template_id == "cinematic"


def test_update_settings_rejects_unknown_template(client):
    from src.apps.comic_gen.api import pipeline
    from src.apps.comic_gen.models import Script

    pipeline.scripts["p2"] = Script(
        id="p2", title="t", original_text="x", created_at=0.0, updated_at=0.0
    )
    r = client.put(
        "/projects/p2/subtitle/settings",
        json={"enabled": True, "template_id": "does_not_exist"},
    )
    assert r.status_code == 400


def test_export_rejects_bad_format(client):
    from src.apps.comic_gen.api import pipeline
    from src.apps.comic_gen.models import Script

    pipeline.scripts["p3"] = Script(
        id="p3", title="t", original_text="x", created_at=0.0, updated_at=0.0
    )
    r = client.get("/projects/p3/subtitle/export", params={"fmt": "vtt"})
    assert r.status_code == 400


def test_bad_style_override_is_400_not_404(client):
    """回归：pydantic 的 ValidationError 继承 ValueError。

    若模型构造写在 `except ValueError -> 404` 里，项目明明存在、只是样式
    参数越界，也会被报成 404，前端会跳到「项目不存在」而不是提示字段错误。
    """
    from src.apps.comic_gen.api import pipeline
    from src.apps.comic_gen.models import Script

    pipeline.scripts["p4"] = Script(
        id="p4", title="t", original_text="x", created_at=0.0, updated_at=0.0
    )
    r = client.put(
        "/projects/p4/subtitle/settings",
        json={"enabled": True, "template_id": "douyin", "style_override": {"alignment": 0}},
    )
    assert r.status_code == 400, r.text


def test_valid_style_override_is_persisted(client):
    from src.apps.comic_gen.api import pipeline
    from src.apps.comic_gen.models import Script

    pipeline.scripts["p5"] = Script(
        id="p5", title="t", original_text="x", created_at=0.0, updated_at=0.0
    )
    r = client.put(
        "/projects/p5/subtitle/settings",
        json={"enabled": True, "template_id": "douyin", "style_override": {"font_size": 48}},
    )
    assert r.status_code == 200
    assert pipeline.scripts["p5"].subtitle_settings.style_override.font_size == 48
