"""Seedance video-to-video: the edit / extend sub-task types.

Contract source: docs/api-reference/byteplus-ark-seedance-seedream.md §2.4.
Editing and extension are NOT separate models and NOT separate modes — they are
sub-types of one omni-reference task, selected with ``omni_reference_task_type``
(``auto`` | ``reference`` | ``edit`` | ``extend``), and only Seedance 2.5 accepts
that parameter at all. The 2.0 series can still edit, but only by letting the
model guess from the prompt.

Each sub-type carries hard constraints Ark rejects the task for. Verified against
the live API on 2026-09-08: that rejection is NOT synchronous, despite the vendor
doc saying so — a violating request gets HTTP 200 and a task id, and only fails
minutes later. The failed task is free, so this is not about money; it is that
these local checks are the only ones that can answer immediately, and they name
what the user did rather than which field was wrong.
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
                       video_url="https://oss.example/clip.mp4",
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
                       video_url="https://oss.example/clip.mp4",
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


# ---------------------------------------------------------------------------
# Service passthrough
#
# The adapter and the playground service were written by two different sessions
# working in parallel, against a shared understanding rather than a shared file.
# These close the loop: a v2v generation assembled the way the API layer
# assembles one has to come out the other end as an Ark body with the source
# video attached and the sub-type set.
# ---------------------------------------------------------------------------

def _v2v_generation(**params):
    from src.apps.playground.models import PlaygroundGeneration, PlaygroundMode

    return PlaygroundGeneration(
        id="gen-1",
        mode=PlaygroundMode.V2V,
        model_id="seedance-2.5-v2v",
        prompt="把天空改成黄昏",
        input_media=["https://oss.example/clip.mp4"],
        parameters=params,
        created_at="2026-09-08T00:00:00Z",
    )


def _capture_ark_body(monkeypatch, gen):
    """Run the service's Seedance path far enough to see the Ark request body."""
    from src.apps.playground.service import PlaygroundService

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["body"] = json
        raise RuntimeError("stop after capture")

    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setattr("src.models.byteplus.requests.post", fake_post)
    monkeypatch.setattr("src.models.byteplus.probe_video_duration", lambda _src: 10.0)

    service = PlaygroundService.__new__(PlaygroundService)
    service._byteplus_video_model = None
    with pytest.raises(RuntimeError, match="stop after capture"):
        service._generate_video_seedance(gen, "out.mp4")
    return captured["body"]


def test_service_attaches_the_source_video_for_v2v(monkeypatch):
    body = _capture_ark_body(monkeypatch, _v2v_generation(aspect_ratio="adaptive"))

    assert {
        "type": "video_url",
        "video_url": {"url": "https://oss.example/clip.mp4"},
        "role": "reference_video",
    } in body["content"]


def test_service_forwards_the_sub_type_to_ark(monkeypatch):
    body = _capture_ark_body(
        monkeypatch, _v2v_generation(task_type="edit", aspect_ratio="adaptive", duration=-1)
    )

    assert body["omni_reference_task_type"] == "edit"


def test_service_omits_the_sub_type_when_none_was_chosen(monkeypatch):
    body = _capture_ark_body(monkeypatch, _v2v_generation(aspect_ratio="adaptive"))

    assert "omni_reference_task_type" not in body


def test_service_surfaces_a_constraint_violation_instead_of_calling_ark(monkeypatch):
    """The UI pins ratio and duration for an edit, but the API accepts a raw
    parameters dict — a caller bypassing the UI still gets stopped locally."""
    from src.apps.playground.service import PlaygroundService

    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setattr(
        "src.models.byteplus.requests.post",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Ark was called")),
    )

    service = PlaygroundService.__new__(PlaygroundService)
    service._byteplus_video_model = None
    gen = _v2v_generation(task_type="edit", aspect_ratio="16:9", duration=5)

    with pytest.raises(ValueError, match="adaptive"):
        service._generate_video_seedance(gen, "out.mp4")


# ---------------------------------------------------------------------------
# Reference images alongside the source clip
#
# This is what the dance-swap flow needs: a character sheet decides who is in
# the shot, the clip decides how they move. Ark takes both in one content array
# (role=reference_image + role=reference_video), but the service used to send
# only the video.
# ---------------------------------------------------------------------------

def _image_items(body):
    return [item for item in body["content"] if item["type"] == "image_url"]


def test_the_source_clip_is_not_also_sent_as_an_image(monkeypatch):
    """Regression: input_media[0] is a video, and the generic first-frame
    resolution used to hand it straight to Ark's image_url field, sending the
    clip twice — once correctly and once as a bogus first frame."""
    body = _capture_ark_body(monkeypatch, _v2v_generation(aspect_ratio="adaptive"))

    assert _image_items(body) == []


def test_trailing_media_entries_become_reference_images(monkeypatch):
    from src.apps.playground.models import PlaygroundGeneration, PlaygroundMode

    gen = PlaygroundGeneration(
        id="gen-2",
        mode=PlaygroundMode.V2V,
        model_id="seedance-2.5-v2v",
        prompt="她跳同一支舞",
        input_media=[
            "https://oss.example/depth.mp4",
            "https://oss.example/sheet.png",
        ],
        parameters={"task_type": "reference", "aspect_ratio": "adaptive"},
        created_at="2026-09-15T00:00:00Z",
    )
    body = _capture_ark_body(monkeypatch, gen)

    assert _image_items(body) == [
        {
            "type": "image_url",
            "image_url": {"url": "https://oss.example/sheet.png"},
            "role": "reference_image",
        }
    ]
    assert {
        "type": "video_url",
        "video_url": {"url": "https://oss.example/depth.mp4"},
        "role": "reference_video",
    } in body["content"]


def test_the_text_item_still_leads_when_both_kinds_are_attached(monkeypatch):
    from src.apps.playground.models import PlaygroundGeneration, PlaygroundMode

    gen = PlaygroundGeneration(
        id="gen-3",
        mode=PlaygroundMode.V2V,
        model_id="seedance-2.5-v2v",
        prompt="她跳同一支舞",
        input_media=["https://oss.example/depth.mp4", "https://oss.example/sheet.png"],
        parameters={"task_type": "reference", "aspect_ratio": "adaptive"},
        created_at="2026-09-15T00:00:00Z",
    )
    body = _capture_ark_body(monkeypatch, gen)

    assert body["content"][0]["type"] == "text"


def test_a_local_clip_without_oss_fails_locally_rather_than_at_ark(model, no_network, monkeypatch):
    """A filesystem path is not something Ark can fetch. Resolving it is the
    adapter's job, and when there is nowhere to upload it the user should be
    told that here — not handed Ark's
    `content[n].video_url.url ... invalid url` from a request that already
    cost a round trip."""
    monkeypatch.setenv("ARK_API_KEY", "test-key")

    with pytest.raises(ValueError, match="URL-compatible"):
        model.generate("她跳同一支舞", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="output/playground/depth/depth_local.mp4",
                       task_type="reference",
                       aspect_ratio="adaptive")


def test_a_remote_clip_is_passed_through_untouched(model, monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["body"] = json
        raise RuntimeError("stop after capture")

    monkeypatch.setenv("ARK_API_KEY", "test-key")
    monkeypatch.setattr("src.models.byteplus.requests.post", fake_post)
    monkeypatch.setattr("src.models.byteplus.probe_video_duration", lambda _src: 10.0)

    with pytest.raises(RuntimeError, match="stop after capture"):
        model.generate("她跳同一支舞", "out.mp4",
                       model_name="seedance-2.5-v2v",
                       video_url="https://oss.example/clip.mp4",
                       task_type="reference",
                       aspect_ratio="adaptive")

    assert {
        "type": "video_url",
        "video_url": {"url": "https://oss.example/clip.mp4"},
        "role": "reference_video",
    } in captured["body"]["content"]
