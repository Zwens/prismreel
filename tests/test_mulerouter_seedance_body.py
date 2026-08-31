"""Seedance request bodies must match the field names the gateway validates.

Contract captured by probing the live endpoint on 2026-08-30. MuleRouter runs
parameter validation BEFORE auth, so the required-field errors below were
observed without a valid API key and without incurring any charge:

  POST /vendors/bytedance/v1/seedance-2.0/reference-to-video/generation
    {"prompt": "p"}                              -> "at least one of 'images'
    {"prompt": "p", "reference_images": [...]}      or 'videos' must be provided"
    {"prompt": "p", "images": [...]}             -> passes validation (401 auth)

  POST .../image-to-video/generation
    {"prompt": "p"}                              -> "'image' expected to be provided"
    {"prompt": "p", "image": "..."}              -> passes validation (401 auth)

R2V was sending `reference_images`, which the gateway ignores entirely — every
reference-to-video call failed validation regardless of credentials.
"""

import pytest

from src.models.mulerouter import MuleRouterVideoModel


@pytest.fixture
def model():
    return MuleRouterVideoModel({})


def test_r2v_body_uses_the_images_field_the_gateway_requires(model):
    body = model._build_r2v_body(
        prompt="a shot",
        img_url="https://example.com/first.png",
        img_path=None,
        ref_image_urls=["https://example.com/ref.png"],
        duration=5,
        resolution="720p",
        aspect_ratio="16:9",
        seed=None,
        watermark=False,
    )

    assert "images" in body, "gateway rejects the payload without 'images'"
    assert body["images"] == [
        "https://example.com/first.png",
        "https://example.com/ref.png",
    ]
    assert "reference_images" not in body, "stale field name the gateway ignores"


def test_r2v_still_refuses_to_build_without_any_image(model):
    with pytest.raises(ValueError):
        model._build_r2v_body(
            prompt="a shot", img_url=None, img_path=None, ref_image_urls=[],
            duration=5, resolution="720p", aspect_ratio="16:9",
            seed=None, watermark=False,
        )


def test_i2v_body_keeps_its_singular_image_field(model):
    body = model._build_i2v_body(
        prompt="a shot", img_url="https://example.com/first.png", img_path=None,
        duration=5, resolution="720p", aspect_ratio="16:9",
        seed=None, watermark=False,
    )

    assert body["image"] == "https://example.com/first.png"


def test_t2v_body_carries_prompt_and_optional_params(model):
    body = model._build_t2v_body(
        prompt="a shot", duration=5, resolution="720p",
        aspect_ratio="16:9", seed=7, watermark=True,
    )

    assert body["prompt"] == "a shot"
    assert body["duration"] == 5
    assert body["resolution"] == "720p"
    assert body["seed"] == 7
