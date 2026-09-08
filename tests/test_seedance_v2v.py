"""Seedance video-to-video: the edit / extend sub-task types.

Contract source: docs/api-reference/byteplus-ark-seedance-seedream.md §2.4.
Editing and extension are NOT separate models and NOT separate modes — they are
sub-types of one omni-reference task, selected with ``omni_reference_task_type``
(``auto`` | ``reference`` | ``edit`` | ``extend``), and only Seedance 2.5 accepts
that parameter at all. The 2.0 series can still edit, but only by letting the
model guess from the prompt.

Each sub-type carries hard constraints that Ark rejects the task for. Ark does
validate them synchronously when the sub-type is explicit, so these local checks
are not the only line of defence — but a rejected task is a wasted round trip on
a request we could already tell was invalid, and the vendor's message names the
field rather than what the user did. So they are checked here, before the POST.
"""

import pytest

from src.models.byteplus import (
    BytePlusVideoModel,
    build_ark_content,
    resolve_ark_model_id,
)


@pytest.fixture
def model():
    return BytePlusVideoModel({})


@pytest.fixture
def no_network(monkeypatch):
    """Fail loudly if a test reaches the network — every rejection below is
    supposed to happen before the POST."""
    def fail(*_args, **_kwargs):
        raise AssertionError("Ark was called; the request should have been rejected first")

    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setattr("src.models.byteplus.requests.post", fail)
    return fail


# ---------------------------------------------------------------------------
# Model id
# ---------------------------------------------------------------------------

def test_v2v_catalog_id_resolves_to_the_two_five_wire_id():
    """The catalog gained seedance-2.5-v2v when v2v was routed to Seedance, but
    an id missing from ARK_MODEL_IDS resolves to None and generate() raises —
    so the mode looks available in the UI and fails on submit."""
    assert resolve_ark_model_id("seedance-2.5-v2v") == "dreamina-seedance-2-5-260628"


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------

def test_source_video_becomes_a_reference_video_content_item():
    content = build_ark_content("延长这段镜头", [], "", videos=["https://oss.example/clip.mp4"])

    video_items = [c for c in content if c.get("type") == "video_url"]
    assert video_items == [
        {
            "type": "video_url",
            "video_url": {"url": "https://oss.example/clip.mp4"},
            "role": "reference_video",
        }
    ]


def test_text_item_still_comes_first_with_a_video_attached():
    content = build_ark_content("延长这段镜头", [], "--ratio adaptive",
                                videos=["https://oss.example/clip.mp4"])

    assert content[0]["type"] == "text"


def test_explicit_sub_type_is_sent_for_two_five(model, monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["body"] = json
        raise RuntimeError("stop after capture")

    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setattr("src.models.byteplus.requests.post", fake_post)

    with pytest.raises(RuntimeError):
        model.generate("延长这段镜头", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="https://oss.example/clip.mp4",
                       task_type="extend",
                       aspect_ratio="adaptive")

    assert captured["body"]["omni_reference_task_type"] == "extend"


def test_sub_type_is_withheld_from_the_two_zero_series(model, monkeypatch):
    """2.0 accepts reference_video but has no omni_reference_task_type
    parameter; sending it would make Ark reject an otherwise valid task."""
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["body"] = json
        raise RuntimeError("stop after capture")

    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setattr("src.models.byteplus.requests.post", fake_post)

    with pytest.raises(RuntimeError):
        model.generate("延长这段镜头", "out.mp4",
                       model_name="seedance-2.0-i2v",
                       video_url="https://oss.example/clip.mp4",
                       task_type="extend",
                       aspect_ratio="adaptive")

    assert "omni_reference_task_type" not in captured["body"]


def test_auto_is_left_unsent_rather_than_spelled_out(model, monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["body"] = json
        raise RuntimeError("stop after capture")

    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setattr("src.models.byteplus.requests.post", fake_post)

    with pytest.raises(RuntimeError):
        model.generate("延长这段镜头", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="https://oss.example/clip.mp4",
                       task_type="auto")

    assert "omni_reference_task_type" not in captured["body"]


# ---------------------------------------------------------------------------
# Pre-flight constraints
# ---------------------------------------------------------------------------

def test_edit_requires_a_source_video(model, no_network):
    with pytest.raises(ValueError, match="reference_video|源视频"):
        model.generate("把天空改成黄昏", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       task_type="edit",
                       aspect_ratio="adaptive", duration=-1)


def test_edit_requires_the_adaptive_ratio(model, no_network):
    with pytest.raises(ValueError, match="adaptive"):
        model.generate("把天空改成黄昏", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="https://oss.example/clip.mp4",
                       task_type="edit",
                       aspect_ratio="16:9", duration=-1)


def test_edit_requires_auto_duration(model, no_network):
    """An edit keeps the source's own length, so Ark only accepts -1."""
    with pytest.raises(ValueError, match="duration|时长"):
        model.generate("把天空改成黄昏", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="https://oss.example/clip.mp4",
                       task_type="edit",
                       aspect_ratio="adaptive", duration=5)


def test_edit_rejects_a_source_video_outside_four_to_thirty_seconds(model, no_network, monkeypatch):
    monkeypatch.setattr("src.models.byteplus.probe_video_duration", lambda _src: 42.0)

    with pytest.raises(ValueError, match="4|30"):
        model.generate("把天空改成黄昏", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="/tmp/clip.mp4",
                       task_type="edit",
                       aspect_ratio="adaptive", duration=-1)


def test_edit_accepts_a_source_video_inside_the_window(model, monkeypatch):
    monkeypatch.setattr("src.models.byteplus.probe_video_duration", lambda _src: 12.0)
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["body"] = json
        raise RuntimeError("stop after capture")

    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setattr("src.models.byteplus.requests.post", fake_post)

    with pytest.raises(RuntimeError):
        model.generate("把天空改成黄昏", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="/tmp/clip.mp4",
                       task_type="edit",
                       aspect_ratio="adaptive", duration=-1)

    assert captured["body"]["omni_reference_task_type"] == "edit"


def test_an_unprobeable_source_is_left_to_ark_rather_than_blocked(model, monkeypatch):
    """A remote URL cannot be probed cheaply. Ark validates an explicit sub-type
    synchronously anyway, so guessing here would only block valid requests."""
    monkeypatch.setattr("src.models.byteplus.probe_video_duration", lambda _src: None)
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["body"] = json
        raise RuntimeError("stop after capture")

    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setattr("src.models.byteplus.requests.post", fake_post)

    with pytest.raises(RuntimeError):
        model.generate("把天空改成黄昏", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="https://oss.example/clip.mp4",
                       task_type="edit",
                       aspect_ratio="adaptive", duration=-1)

    assert captured["body"]["omni_reference_task_type"] == "edit"


def test_extend_requires_the_adaptive_ratio(model, no_network):
    with pytest.raises(ValueError, match="adaptive"):
        model.generate("继续往前走", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="https://oss.example/clip.mp4",
                       task_type="extend",
                       aspect_ratio="1:1")


def test_extend_does_not_force_auto_duration(model, monkeypatch):
    """Unlike edit, an extension produces new footage of its own length."""
    monkeypatch.setattr("src.models.byteplus.probe_video_duration", lambda _src: 8.0)
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["body"] = json
        raise RuntimeError("stop after capture")

    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setattr("src.models.byteplus.requests.post", fake_post)

    with pytest.raises(RuntimeError):
        model.generate("继续往前走", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="https://oss.example/clip.mp4",
                       task_type="extend",
                       aspect_ratio="adaptive", duration=6)

    assert captured["body"]["omni_reference_task_type"] == "extend"


def test_an_unknown_sub_type_is_rejected_locally(model, no_network):
    with pytest.raises(ValueError, match="task_type|子类型"):
        model.generate("继续往前走", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="https://oss.example/clip.mp4",
                       task_type="rewrite")
