import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.apps.comic_gen.models import VideoTask
from src.apps.comic_gen.pipeline import ComicGenPipeline
from src.models.vidu import ViduModel, to_vendor_model


PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4//8/AwAI/AL+"
    "X2VINQAAAABJRU5ErkJggg=="
)


class _FakeResponse:
    def __init__(self, status_code, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.text = str(self._payload)

    def json(self):
        return self._payload


def _build_pipeline(task: VideoTask, wanx_model) -> ComicGenPipeline:
    pipeline = ComicGenPipeline.__new__(ComicGenPipeline)
    script = SimpleNamespace(
        id=task.project_id,
        video_tasks=[task],
        characters=[],
        scenes=[],
        props=[],
        updated_at=0,
    )
    pipeline.scripts = {task.project_id: script}
    pipeline._save_data = lambda: None
    pipeline._download_temp_image = lambda _: "/tmp/downloaded-vidu.png"
    pipeline._kling_model = None
    pipeline._vidu_model = None
    pipeline.video_generator = SimpleNamespace(model=wanx_model)
    pipeline.get_script = lambda script_id: pipeline.scripts.get(script_id)
    return pipeline


def _write_output_png(rel_path: str) -> str:
    file_path = Path("output") / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(base64.b64decode(PNG_1X1_BASE64))
    return str(file_path.resolve())


def test_pipeline_routes_vidu_vendor_mode_to_vendor_adapter(monkeypatch):
    monkeypatch.setenv("VIDU_PROVIDER_MODE", "vendor")

    task = VideoTask(
        id="task-vidu-vendor",
        project_id="script-1",
        image_url="https://example.com/ref.png",
        prompt="demo",
        model="viduq3-pro",
    )

    calls = {}

    class FakeViduModel:
        def __init__(self, config):
            calls["init_config"] = config

        def generate(self, **kwargs):
            calls["vendor_kwargs"] = kwargs
            return kwargs["output_path"], 0.0

    class FakeWanxModel:
        def generate(self, **kwargs):
            calls["wanx_kwargs"] = kwargs
            raise AssertionError("DashScope path should not be used in vendor mode")

    monkeypatch.setattr("src.models.vidu.ViduModel", FakeViduModel)

    pipeline = _build_pipeline(task, FakeWanxModel())
    pipeline.process_video_task("script-1", "task-vidu-vendor")

    assert "vendor_kwargs" in calls
    assert "wanx_kwargs" not in calls
    assert calls["vendor_kwargs"]["model"] == "viduq3-pro"
    assert calls["vendor_kwargs"]["img_path"] == "/tmp/downloaded-vidu.png"
    assert task.status == "completed"


def test_pipeline_routes_vidu_dashscope_mode_to_wanx_without_vendor_credentials(monkeypatch):
    monkeypatch.setenv("VIDU_PROVIDER_MODE", "dashscope")
    monkeypatch.delenv("VIDU_API_KEY", raising=False)

    task = VideoTask(
        id="task-vidu-dashscope",
        project_id="script-1",
        image_url="https://example.com/ref.png",
        prompt="demo",
        model="viduq3-pro",
    )

    calls = {}

    class FakeViduModel:
        def __init__(self, config):
            calls["vendor_init"] = config

        def generate(self, **kwargs):
            calls["vendor_kwargs"] = kwargs
            raise AssertionError("Vendor adapter should not be used in dashscope mode")

    class FakeWanxModel:
        def generate(self, **kwargs):
            calls["wanx_kwargs"] = kwargs
            return kwargs["output_path"], 0.0

    monkeypatch.setattr("src.models.vidu.ViduModel", FakeViduModel)

    pipeline = _build_pipeline(task, FakeWanxModel())
    pipeline.process_video_task("script-1", "task-vidu-dashscope")

    assert "wanx_kwargs" in calls
    assert "vendor_kwargs" not in calls
    assert calls["wanx_kwargs"]["model"] == "viduq3-pro"
    assert calls["wanx_kwargs"]["img_path"] == "/tmp/downloaded-vidu.png"
    assert task.status == "completed"


def test_vendor_vidu_local_image_without_oss_fails_clearly(monkeypatch, tmp_path):
    local_path = _write_output_png("uploads/test_vidu_vendor_ref_no_oss.png")

    class FakeUploader:
        def __init__(self):
            self.is_configured = False

    monkeypatch.setattr("src.models.vidu.OSSImageUploader", FakeUploader)

    model = ViduModel({"api_key": "test-key"})

    with pytest.raises(ValueError, match="requires a URL-compatible media source"):
        model.generate(
            prompt="demo",
            output_path=str(tmp_path / "out.mp4"),
            img_path=local_path,
            model="viduq3-pro",
        )


def test_vendor_vidu_local_image_with_oss_uses_signed_url(monkeypatch, tmp_path):
    captured = {}
    local_path = _write_output_png("uploads/test_vidu_vendor_ref_with_oss.png")

    class FakeUploader:
        def __init__(self):
            self.is_configured = True

        def upload_file(self, local_path, sub_path="", custom_filename=None):
            filename = custom_filename or Path(local_path).name
            return f"prismreel/{sub_path.strip('/')}/{filename}".replace("//", "/")

        def sign_url_for_api(self, object_key):
            return f"https://oss.example/{object_key}"

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["submit_url"] = url
        captured["headers"] = dict(headers or {})
        captured["body"] = json or {}
        return _FakeResponse(200, {"task_id": "vidu-task-1"})

    def fake_get(url, headers=None, timeout=None):
        if "tasks" in url:
            return _FakeResponse(
                200,
                {"state": "success", "creations": [{"url": "https://example.com/out.mp4"}]},
            )
        return _FakeResponse(200, content=b"video")

    monkeypatch.setattr("src.models.vidu.OSSImageUploader", FakeUploader)
    monkeypatch.setattr("src.models.vidu.requests.post", fake_post)
    monkeypatch.setattr("src.models.vidu.requests.get", fake_get)
    monkeypatch.setattr("src.models.vidu.time.sleep", lambda _: None)

    model = ViduModel({"api_key": "test-key"})
    model.generate(
        prompt="demo",
        output_path=str(tmp_path / "out.mp4"),
        img_path=local_path,
        model="viduq3-pro",
    )

    assert captured["submit_url"].endswith("/img2video")
    assert captured["headers"]["Authorization"] == "Token test-key"
    assert captured["body"]["images"][0].startswith("https://oss.example/prismreel/")


@pytest.mark.parametrize(
    "catalog_id,expected",
    [
        ("viduq3-drama-r2v", "viduq3-drama"),
        ("viduq3-drama", "viduq3-drama"),
        ("vidu/viduq3-drama-video", "viduq3-drama"),
        ("viduq3-pro-i2v", "viduq3-pro"),
        ("viduq3-pro-r2v", "viduq3-pro"),
        ("viduq3-turbo-i2v", "viduq3-turbo"),
        ("vidu/viduq3-pro-video", "viduq3-pro"),
        ("viduq3-pro", "viduq3-pro"),
    ],
)
def test_catalog_ids_normalize_to_vendor_model_names(catalog_id, expected):
    """The vendor API rejects catalog ids verbatim (FieldInvalid: model is not
    supported) — only the bare model name is accepted."""
    assert to_vendor_model(catalog_id, "fallback") == expected


def test_to_vendor_model_falls_back_when_unset():
    assert to_vendor_model(None, "viduq3-drama") == "viduq3-drama"
    assert to_vendor_model("", "viduq3-drama") == "viduq3-drama"


def test_vendor_vidu_r2v_hits_reference2video_with_bare_model_name(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["submit_url"] = url
        captured["body"] = json or {}
        return _FakeResponse(200, {"task_id": "vidu-r2v-1"})

    def fake_get(url, headers=None, timeout=None):
        if "tasks" in url:
            return _FakeResponse(
                200,
                {"state": "success", "creations": [{"url": "https://example.com/out.mp4"}]},
            )
        return _FakeResponse(200, content=b"video")

    monkeypatch.setattr("src.models.vidu.requests.post", fake_post)
    monkeypatch.setattr("src.models.vidu.requests.get", fake_get)
    monkeypatch.setattr("src.models.vidu.time.sleep", lambda _: None)

    model = ViduModel({"api_key": "test-key"})
    model.generate(
        prompt="two characters argue in the rain",
        output_path=str(tmp_path / "out.mp4"),
        model="viduq3-drama-r2v",
        generation_mode="r2v",
        ref_image_urls=["https://cdn.example/a.png", "https://cdn.example/b.png"],
        duration=8,
        resolution="1080p",
        watermark=False,
    )

    assert captured["submit_url"].endswith("/reference2video")
    assert captured["body"]["model"] == "viduq3-drama"
    assert captured["body"]["images"] == [
        "https://cdn.example/a.png",
        "https://cdn.example/b.png",
    ]
    assert captured["body"]["duration"] == 8
    assert captured["body"]["watermark"] is False
    # Unset aspect_ratio must be omitted so viduq3-drama keeps its 9:16 default.
    assert "aspect_ratio" not in captured["body"]


def test_vendor_vidu_r2v_without_references_fails_clearly(tmp_path):
    model = ViduModel({"api_key": "test-key"})

    with pytest.raises(ValueError, match="at least one reference image"):
        model.generate(
            prompt="demo",
            output_path=str(tmp_path / "out.mp4"),
            model="viduq3-drama-r2v",
            generation_mode="r2v",
            ref_image_urls=[],
        )


def test_poll_survives_transient_network_error(monkeypatch, tmp_path):
    """The task is already submitted and billed once polling starts, so a
    dropped connection must not discard the result."""
    import requests as _requests

    state = {"calls": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResponse(200, {"task_id": "vidu-flaky-1"})

    def fake_get(url, headers=None, timeout=None):
        if "tasks" in url:
            state["calls"] += 1
            if state["calls"] == 1:
                raise _requests.ConnectionError("Connection aborted.")
            return _FakeResponse(
                200,
                {"state": "success", "creations": [{"url": "https://example.com/out.mp4"}]},
            )
        return _FakeResponse(200, content=b"video")

    monkeypatch.setattr("src.models.vidu.requests.post", fake_post)
    monkeypatch.setattr("src.models.vidu.requests.get", fake_get)
    monkeypatch.setattr("src.models.vidu.time.sleep", lambda _: None)

    model = ViduModel({"api_key": "test-key"})
    out_path, _ = model.generate(
        prompt="demo",
        output_path=str(tmp_path / "out.mp4"),
        model="viduq3-drama-r2v",
        generation_mode="r2v",
        ref_image_urls=["https://cdn.example/a.png"],
    )

    assert state["calls"] == 2  # first raised, second succeeded
    assert out_path == str(tmp_path / "out.mp4")


def test_pipeline_forwards_r2v_references_to_vendor_vidu(monkeypatch):
    """Regression: the vendor branch used to drop generation_mode and
    reference_image_urls, so R2V could never reach reference2video."""
    monkeypatch.setenv("VIDU_PROVIDER_MODE", "vendor")

    task = VideoTask(
        id="task-vidu-r2v",
        project_id="script-1",
        image_url="",
        prompt="demo",
        model="viduq3-drama-r2v",
        generation_mode="r2v",
        reference_image_urls=["https://cdn.example/a.png"],
    )

    calls = {}

    class FakeViduModel:
        def __init__(self, config):
            pass

        def generate(self, **kwargs):
            calls["vendor_kwargs"] = kwargs
            return kwargs["output_path"], 0.0

    class FakeWanxModel:
        def generate(self, **kwargs):
            raise AssertionError("DashScope path should not be used in vendor mode")

    monkeypatch.setattr("src.models.vidu.ViduModel", FakeViduModel)

    pipeline = _build_pipeline(task, FakeWanxModel())
    pipeline.process_video_task("script-1", "task-vidu-r2v")

    kwargs = calls["vendor_kwargs"]
    assert kwargs["generation_mode"] == "r2v"
    assert kwargs["ref_image_urls"] == ["https://cdn.example/a.png"]
    assert kwargs["model"] == "viduq3-drama-r2v"
    assert task.status == "completed"


# --- Vendor /reference2video model whitelist -------------------------------
# The vendor endpoint accepts a fixed model set (Vidu 参考生 API Q3, rev.
# 2026-08-24): viduq3-drama / viduq3-ad / viduq3-mix / viduq3-turbo / viduq3 /
# viduq2-pro / viduq2 / viduq1 / vidu2.0. Notably absent: viduq3-pro, which is
# an i2v/t2v-only line. Stripping the mode suffix off the catalog id
# (viduq3-pro-r2v -> viduq3-pro) therefore produces a name the endpoint
# rejects with FieldInvalid "model is not supported".


@pytest.mark.parametrize(
    "catalog_id,expected",
    [
        ("viduq3-pro-r2v", "viduq3-mix"),
        ("viduq3-turbo-r2v", "viduq3-turbo"),
        ("viduq3-drama-r2v", "viduq3-drama"),
    ],
)
def test_r2v_catalog_ids_resolve_to_endpoint_supported_models(catalog_id, expected):
    from src.models.vidu import resolve_r2v_vendor_model

    assert resolve_r2v_vendor_model(catalog_id) == expected


def test_r2v_resolution_never_yields_an_unsupported_model():
    from src.models.vidu import VENDOR_R2V_MODELS, resolve_r2v_vendor_model

    for catalog_id in ("viduq3-pro-r2v", "viduq3-turbo-r2v", "viduq3-drama-r2v"):
        assert resolve_r2v_vendor_model(catalog_id) in VENDOR_R2V_MODELS


def test_r2v_rejects_unsupported_model_locally_without_calling_the_api(monkeypatch):
    """A model the endpoint cannot serve must fail fast with a readable error
    instead of burning a round-trip on an HTTP 400 FieldInvalid."""
    called = {"post": False}

    def fake_post(*args, **kwargs):
        called["post"] = True
        raise AssertionError("must not reach the vendor API")

    monkeypatch.setattr("src.models.vidu.requests.post", fake_post)
    model = ViduModel({"api_key": "test-key"})

    with pytest.raises(ValueError) as excinfo:
        model._submit_r2v(
            prompt="hello",
            image_urls=["https://example.com/a.png"],
            model="viduq3-bogusname",
        )

    message = str(excinfo.value)
    assert "viduq3-bogusname" in message
    assert "reference2video" in message or "r2v" in message
    assert called["post"] is False


def test_r2v_submits_a_whitelisted_model_for_the_pro_catalog_id(monkeypatch):
    """Regression for the HTTP 400 storm: viduq3-pro-r2v used to submit
    model=viduq3-pro, which /reference2video rejects."""
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["submit_url"] = url
        captured["body"] = json or {}
        return _FakeResponse(200, {"task_id": "vidu-r2v-pro"})

    monkeypatch.setattr("src.models.vidu.requests.post", fake_post)
    model = ViduModel({"api_key": "test-key"})

    task_id, used_model = model._submit_r2v(
        prompt="hello",
        image_urls=["https://example.com/a.png"],
        model="viduq3-pro-r2v",
    )

    from src.models.vidu import VENDOR_R2V_MODELS

    assert task_id == "vidu-r2v-pro"
    assert used_model != "viduq3-pro"
    assert captured["body"]["model"] in VENDOR_R2V_MODELS
    assert captured["body"]["model"] == used_model


def test_failed_video_task_records_the_reason(monkeypatch):
    """A failed task must carry its reason, not just a red dot. Without this the
    queue panel's diagnostics copy back `"error": null` and the only trace of
    the failure is the server log."""
    monkeypatch.setenv("VIDU_PROVIDER_MODE", "vendor")

    task = VideoTask(
        id="task-vidu-failure",
        project_id="script-1",
        image_url="https://example.com/ref.png",
        prompt="demo",
        model="viduq3-pro",
    )

    class ExplodingViduModel:
        def __init__(self, config):
            pass

        def generate(self, **kwargs):
            raise RuntimeError(
                "Vidu r2v submission failed (HTTP 400): model is not supported"
            )

    class FakeWanxModel:
        def generate(self, **kwargs):
            raise AssertionError("DashScope path should not be used in vendor mode")

    monkeypatch.setattr("src.models.vidu.ViduModel", ExplodingViduModel)

    pipeline = _build_pipeline(task, FakeWanxModel())
    pipeline.process_video_task("script-1", "task-vidu-failure")

    assert task.status == "failed"
    assert task.error, "failed task must record why it failed"
    assert "model is not supported" in task.error


@pytest.mark.parametrize(
    "canonical_id,expected",
    [
        ("vidu/viduq3-pro-video#r2v", "viduq3-mix"),
        ("vidu/viduq3-turbo-video#r2v", "viduq3-turbo"),
        ("vidu/viduq3-drama-video#r2v", "viduq3-drama"),
    ],
)
def test_r2v_canonical_mode_ids_resolve_too(canonical_id, expected):
    """Canonical mode ids circulate alongside legacy flat ids (the catalog's own
    defaults are canonical), so the resolver has to accept both forms."""
    from src.models.vidu import resolve_r2v_vendor_model

    assert resolve_r2v_vendor_model(canonical_id) == expected
