"""BytePlus ModelArk (Seedance 2.5) request construction.

Contract source: this repo's own Ark SDK usage in src/models/doubao.py —
`content_generation.tasks.create(model=..., content=[{type: text, ...},
{type: image_url, image_url: {url: ...}}])` with generation parameters passed
as `--flag value` tokens appended to the text item. The REST surface used here
is the same Ark v3 API the SDK wraps.

Verified live on 2026-08-30: both `ark.ap-southeast.bytepluses.com` (BytePlus,
international) and `ark.cn-beijing.volces.com` (Volcano, China) answer with
`401 AuthenticationError`, so the hosts and the v3 prefix are real. Unlike
MuleRouter, auth is checked BEFORE parameter validation, so the request schema
could NOT be probed without a key — everything below is pinned to the SDK
usage above, and the host / path / model id are env-overridable so a mismatch
is a config change rather than a code change.
"""

import pytest

from src.models.byteplus import (
    BytePlusVideoModel,
    build_ark_content,
    build_param_flags,
    resolve_ark_base_url,
)


@pytest.fixture
def model():
    return BytePlusVideoModel({})


# ---------------------------------------------------------------------------
# Parameter flags
# ---------------------------------------------------------------------------

def test_param_flags_render_in_ark_token_form():
    flags = build_param_flags(resolution="1080p", duration=8, ratio="16:9", watermark=False)

    assert "--resolution 1080p" in flags
    assert "--duration 8" in flags
    assert "--ratio 16:9" in flags
    assert "--watermark false" in flags


def test_param_flags_omit_unset_values():
    flags = build_param_flags(resolution=None, duration=None, ratio=None, watermark=None)

    assert flags == ""


def test_watermark_true_renders_lowercase():
    """Ark parses these tokens as text; Python's True would not match."""
    assert "--watermark true" in build_param_flags(
        resolution=None, duration=None, ratio=None, watermark=True
    )


# ---------------------------------------------------------------------------
# Content array
# ---------------------------------------------------------------------------

def test_t2v_content_is_text_only():
    content = build_ark_content("a shot", images=[], flags="--duration 5")

    assert content == [{"type": "text", "text": "a shot --duration 5"}]


def test_i2v_content_appends_a_single_image_item():
    content = build_ark_content("a shot", images=["https://x/first.png"], flags="")

    assert content[0] == {"type": "text", "text": "a shot"}
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://x/first.png"},
    }


def test_r2v_content_carries_every_reference_in_order():
    images = [f"https://x/{i}.png" for i in range(4)]

    content = build_ark_content("a shot", images=images, flags="")

    urls = [c["image_url"]["url"] for c in content if c["type"] == "image_url"]
    assert urls == images


def test_prompt_and_flags_are_joined_with_a_single_space():
    content = build_ark_content("  a shot  ", images=[], flags="--duration 5")

    assert content[0]["text"] == "a shot --duration 5"


# ---------------------------------------------------------------------------
# Host selection
# ---------------------------------------------------------------------------

def test_international_host_is_the_default(monkeypatch):
    monkeypatch.delenv("ARK_BASE_URL", raising=False)
    monkeypatch.delenv("ARK_REGION", raising=False)

    assert "bytepluses.com" in resolve_ark_base_url()


def test_china_region_selects_the_volces_host(monkeypatch):
    monkeypatch.delenv("ARK_BASE_URL", raising=False)
    monkeypatch.setenv("ARK_REGION", "cn")

    assert "volces.com" in resolve_ark_base_url()


def test_explicit_base_url_overrides_region(monkeypatch):
    """The endpoint could not be verified without a key — an override keeps a
    wrong default from requiring a code change."""
    monkeypatch.setenv("ARK_REGION", "cn")
    monkeypatch.setenv("ARK_BASE_URL", "https://custom.example/api/v3")

    assert resolve_ark_base_url() == "https://custom.example/api/v3"


# ---------------------------------------------------------------------------
# Model id resolution
# ---------------------------------------------------------------------------

def test_model_id_comes_from_the_call_not_the_instance(model):
    """The pipeline caches one model instance across shots, so the id has to
    travel with the request."""
    assert model.resolve_model_id("seedance-2.5-r2v") == "dreamina-seedance-2-5-260628"


def test_unknown_model_id_passes_through_untouched(model):
    assert model.resolve_model_id("some-future-id") == "some-future-id"
