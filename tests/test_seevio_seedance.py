"""Seedance via Seevio (api.seevio.ai) request construction.

Contract source: https://seevio.ai/zh-hant/api-docs, captured 2026-08-31 into
docs/api-reference/seedance-seevio.md. Seevio is the aggregator that issues
this project's Seedance keys (sk_live_ / sk_test_); it is neither MuleRouter
nor ByteDance-direct, and its wire format overlaps with neither. Before this
adapter existed the Seevio key was sitting in ARK_API_KEY, being sent to
ark.ap-southeast.bytepluses.com in Ark's request format — a guaranteed failure.

Not yet exercised against a live key, so these tests pin the documented
contract, not observed gateway behaviour. The base URL is env-overridable
(SEEVIO_BASE_URL) precisely because of that.
"""

import pytest

from src.models.seevio import (
    SeevioVideoModel,
    resolve_seevio_model_id,
)


@pytest.fixture
def model():
    return SeevioVideoModel({})


# ---------------------------------------------------------------------------
# Wire model ids
# ---------------------------------------------------------------------------

def test_catalog_ids_map_to_hyphenated_wire_ids():
    """Seevio spells versions with hyphens where the catalog uses dots."""
    assert resolve_seevio_model_id("seedance-2.0-t2v") == "seedance-2-0"
    assert resolve_seevio_model_id("seedance-2.5-r2v") == "seedance-2-5"


def test_fast_variant_never_falls_back_to_standard():
    """`-fast` bills differently, so a near-miss must not resolve to standard."""
    assert resolve_seevio_model_id("seedance-2.0-fast-i2v") == "seedance-2-0-fast"
    assert (
        resolve_seevio_model_id("seedance/seedance-2.0-fast-video#i2v")
        == "seedance-2-0-fast"
    )


def test_canonical_mode_ids_resolve():
    assert (
        resolve_seevio_model_id("seedance/seedance-2.5-video#r2v") == "seedance-2-5"
    )
    assert resolve_seevio_model_id("seedance/seedance-2.0-video#t2v") == "seedance-2-0"


def test_unknown_id_passes_through():
    """Lets a newly released Seevio model be pinned without a code change."""
    assert resolve_seevio_model_id("seedance-3-0") == "seedance-3-0"


# ---------------------------------------------------------------------------
# Request body
# ---------------------------------------------------------------------------

def _body(model, **overrides):
    kwargs = dict(
        prompt="a cat surfing on a neon wave",
        generation_type="text-to-video",
        model_id="seedance-2-5",
        image_urls=[],
        duration=5,
        resolution="1080p",
        aspect_ratio="16:9",
        seed=None,
        watermark=False,
    )
    kwargs.update(overrides)
    return model._build_body(**kwargs)


def test_body_nests_everything_but_model_under_input(model):
    """Seevio takes `{model, input: {...}}` — a flat body is MuleRouter's shape."""
    body = _body(model)

    assert set(body) == {"model", "input"}
    assert body["model"] == "seedance-2-5"
    assert body["input"]["prompt"] == "a cat surfing on a neon wave"
    assert body["input"]["generation_type"] == "text-to-video"


def test_generation_type_is_required_on_every_mode(model):
    for gen_type in ("text-to-video", "image-to-video", "reference-to-video"):
        assert _body(model, generation_type=gen_type)["input"]["generation_type"] == gen_type


def test_reference_images_travel_as_image_urls(model):
    """The field is `image_urls` (plural, an array) — not `image`, not
    `reference_images`. Getting this name wrong is exactly what made R2V fail
    100% of the time on the MuleRouter path."""
    urls = ["https://example.com/a.png", "https://example.com/b.png"]
    body = _body(model, generation_type="reference-to-video", image_urls=urls)

    assert body["input"]["image_urls"] == urls
    assert "image" not in body["input"]
    assert "reference_images" not in body["input"]


def test_empty_image_list_is_omitted(model):
    """t2v must not send an empty array — omit rather than send a falsy value."""
    assert "image_urls" not in _body(model)["input"]


def test_unset_seed_is_omitted(model):
    """`seed` is undocumented; sending it unsolicited is what would trip a
    strict validator, so it appears only when the user pinned one."""
    assert "seed" not in _body(model)["input"]
    assert _body(model, seed=42)["input"]["seed"] == 42


def test_watermark_false_is_still_sent(model):
    """False is a meaningful choice here, not an absent value."""
    assert _body(model, watermark=False)["input"]["watermark"] is False


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_missing_key_names_the_right_variable(model, monkeypatch):
    """The failure this whole adapter exists to prevent was a Seevio key sitting
    in ARK_API_KEY, so the error has to name SEEVIO_API_KEY explicitly."""
    monkeypatch.delenv("SEEVIO_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SEEVIO_API_KEY"):
        model._headers()


def test_bearer_auth(model, monkeypatch):
    monkeypatch.setenv("SEEVIO_API_KEY", "sk_live_abc")

    assert model._headers()["Authorization"] == "Bearer sk_live_abc"


def test_base_url_is_env_overridable(model, monkeypatch):
    monkeypatch.delenv("SEEVIO_BASE_URL", raising=False)
    assert model._base_url() == "https://api.seevio.ai"

    monkeypatch.setenv("SEEVIO_BASE_URL", "https://staging.seevio.ai/")
    assert model._base_url() == "https://staging.seevio.ai"


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_poll_reads_the_url_out_of_data_results(model, monkeypatch):
    """Seevio nests the finished video under data.results[] — a flat
    `video_url` is Ark's shape, not this one."""
    monkeypatch.setenv("SEEVIO_API_KEY", "sk_live_abc")
    monkeypatch.setattr(
        "src.models.seevio.requests.get",
        lambda *a, **k: _FakeResponse(
            {
                "id": "t1",
                "status": "completed",
                "data": {"results": ["https://cdn.seevio.ai/x.mp4"]},
            }
        ),
    )

    assert model._poll("t1") == "https://cdn.seevio.ai/x.mp4"


def test_poll_surfaces_failed_reason(model, monkeypatch):
    monkeypatch.setenv("SEEVIO_API_KEY", "sk_live_abc")
    monkeypatch.setattr(
        "src.models.seevio.requests.get",
        lambda *a, **k: _FakeResponse(
            {"id": "t1", "status": "failed", "failed_reason": "provider_failed"}
        ),
    )

    with pytest.raises(RuntimeError, match="provider_failed"):
        model._poll("t1")


def test_completed_without_a_url_is_an_error_not_a_silent_none(model, monkeypatch):
    monkeypatch.setenv("SEEVIO_API_KEY", "sk_live_abc")
    monkeypatch.setattr(
        "src.models.seevio.requests.get",
        lambda *a, **k: _FakeResponse({"id": "t1", "status": "completed", "data": {"results": []}}),
    )

    with pytest.raises(RuntimeError, match="without a video url"):
        model._poll("t1")
