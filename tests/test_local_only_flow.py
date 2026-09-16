import base64
import time
from pathlib import Path
from types import SimpleNamespace

from src.apps.comic_gen.models import Character, Scene, Script, StoryboardFrame
from src.apps.comic_gen.pipeline import ComicGenPipeline
from src.models.byteplus import BytePlusVideoModel


PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4//8/AwAI/AL+"
    "X2VINQAAAABJRU5ErkJggg=="
)


def _write_output_png(rel_path: str) -> str:
    file_path = Path("output") / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(base64.b64decode(PNG_1X1_BASE64))
    return str(file_path)


def _build_pipeline(script: Script, video_model: BytePlusVideoModel) -> ComicGenPipeline:
    pipeline = ComicGenPipeline.__new__(ComicGenPipeline)
    pipeline.scripts = {script.id: script}
    pipeline._save_data = lambda: None
    pipeline._kling_model = None
    pipeline._vidu_model = None
    pipeline.video_generator = SimpleNamespace(model=video_model)
    pipeline._byteplus_video_model = video_model
    pipeline.get_script = lambda script_id: pipeline.scripts.get(script_id)
    return pipeline


def test_local_only_pipeline_flow_without_oss(monkeypatch):
    """
    End-to-end backend check for local-only mode:
    - local uploaded/generated/storyboard refs stay as stable project refs
    - video task snapshots local input under output/video_inputs
    - DashScope I2V media prep works without OSS via temp oss:// URL + resolve header
    """
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    for key in (
        "ALIBABA_CLOUD_ACCESS_KEY_ID",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        "OSS_BUCKET_NAME",
        "OSS_ENDPOINT",
        "KLING_ACCESS_KEY",
        "KLING_SECRET_KEY",
        "VIDU_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    _write_output_png("uploads/local_only_uploaded.png")
    _write_output_png("assets/scenes/local_only_generated.png")
    _write_output_png("storyboard/local_only_frame.png")

    now = time.time()
    character = Character(
        id="char-local",
        name="Local Hero",
        description="A character from local-only flow",
        image_url="uploads/local_only_uploaded.png",
    )
    scene = Scene(
        id="scene-local",
        name="Local Scene",
        description="A scene generated in local-only flow",
        image_url="assets/scenes/local_only_generated.png",
    )
    frame = StoryboardFrame(
        id="frame-local",
        scene_id=scene.id,
        character_ids=[character.id],
        prop_ids=[],
        rendered_image_url="storyboard/local_only_frame.png",
    )
    script = Script(
        id="script-local-only",
        title="Local-Only",
        original_text="demo",
        characters=[character],
        scenes=[scene],
        frames=[frame],
        created_at=now,
        updated_at=now,
    )

    captured = {}

    video_model = BytePlusVideoModel({"params": {}})

    class _Resp:
        status_code = 200
        text = ""
        def raise_for_status(self): pass
        def json(self): return {"id": "task-local-only"}

    def fake_post(url, json=None, headers=None, timeout=None, **_kw):
        # content 数组里那条 image_url 就是请求期变换后的地址；断言它没有
        # 反过来写进项目数据，是这个用例的核心。
        for item in (json or {}).get("content", []):
            if item.get("type") == "image_url":
                captured["img_url"] = item["image_url"]["url"]
        captured["model_name"] = (json or {}).get("model")
        return _Resp()

    def fake_poll(_task_id: str) -> str:
        return "https://example.com/local-only-video.mp4"

    def fake_download(_url: str, output_path: str):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"video")

    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
    monkeypatch.setattr("src.models.byteplus.requests.post", fake_post)
    monkeypatch.setattr(video_model, "_poll", fake_poll)
    monkeypatch.setattr(video_model, "_download", fake_download)

    pipeline = _build_pipeline(script, video_model)

    _, task_id = pipeline.create_video_task(
        script_id=script.id,
        image_url=frame.rendered_image_url,
        prompt="Pan and zoom on the character",
        model="seedance-2.5-i2v",
    )
    task = next(t for t in script.video_tasks if t.id == task_id)

    assert task.image_url.startswith("video_inputs/")
    assert (Path("output") / task.image_url).exists()

    pipeline.process_video_task(script.id, task_id)

    # Ark 只接受厂商可 GET 的地址（见 docs/api-reference/byteplus-ark-seedance-
    # seedream.md），没有 base64 内联这条路。所以不配 OSS 时，一张本地首帧根本
    # 递不到 Seedance 手里——适配器在发请求前就拒绝，并指明要配 OSS。
    #
    # 这个用例此前断言 completed，只是因为 requests.post 被 mock 掉了：真实调用
    # 会把 'video_inputs/xxx.png' 原样塞进 image_url，由 Ark 侧失败。现在改为钉住
    # 那条可操作的错误。
    assert task.status == "failed"
    assert "OSS" in (task.error or "")

    # DashScope 专属的临时 URL / OssResourceResolve 头随 wanx 适配器一并消失，
    # 相关断言不再适用。本用例保留的核心价值是下面这条：请求期的地址变换不得
    # 回写进项目数据——任务失败时同样不许回写。

    # Stable project refs remain local refs; request-side transforms are not persisted.
    assert script.characters[0].image_url == "uploads/local_only_uploaded.png"
    assert script.scenes[0].image_url == "assets/scenes/local_only_generated.png"
    assert script.frames[0].rendered_image_url == "storyboard/local_only_frame.png"
