"""Vidu image generation (O-protocol sync endpoint) adapter tests.

Covers the three things that silently break when the vendor contract is
misread: model-id normalization, size snapping, and the request payload shape.
"""

import pytest

from src.models.image import WanxImageModel, resolve_image_adapter
from src.models.vidu import (
    ViduImageModel,
    is_vidu_image_model,
    normalize_vidu_image_size,
    to_vendor_image_model,
)


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


def _ok_payload(url="https://cdn.vidu.cn/api/image.png"):
    # Mirrors a real response: note `created` is a *string*, not the integer the
    # published example shows.
    return {
        "created": "1787585699",
        "data": [{"url": url}],
        "credits": 8,
        "usageMetadata": {"totalTokenCount": 1539},
    }


# ---------------------------------------------------------------------------
# Model id normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "catalog_id,expected",
    [
        ("vidu/vidu-q3-lite-image", "q3-lite"),
        ("vidu/vidu-q3-fast-image", "q3-fast"),
        ("vidu-q3-fast-image", "q3-fast"),
        ("q3-fast", "q3-fast"),
        ("q3-fast-bytoken", "q3-fast-bytoken"),
        (None, "q3-lite"),
        ("", "q3-lite"),
    ],
)
def test_to_vendor_image_model(catalog_id, expected):
    assert to_vendor_image_model(catalog_id) == expected


@pytest.mark.parametrize(
    "model_id,expected",
    [
        ("vidu/vidu-q3-lite-image", True),
        ("vidu/vidu-q3-fast-image", True),
        ("q3-lite", True),
        ("q2-pro-bytoken", True),
        # The whole point of keying on the -image suffix: video ids must not match.
        ("vidu/viduq3-pro-video", False),
        ("viduq3-drama-r2v", False),
        ("gpt-image-2", False),
        ("wan2.7-image-pro", False),
        ("", False),
        (None, False),
    ],
)
def test_is_vidu_image_model(model_id, expected):
    assert is_vidu_image_model(model_id) is expected


# ---------------------------------------------------------------------------
# Size snapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "requested,expected",
    [
        # The app speaks DashScope's '576*1024'; Vidu only takes its own table.
        ("576*1024", "768x1376"),   # 9:16 portrait
        ("1024*576", "1376x768"),   # 16:9 landscape
        ("1280*720", "1376x768"),   # 16:9, non-listed dimensions
        ("768*1024", "896x1200"),   # 3:4
        # Exact matches pass through untouched.
        ("1024x1024", "1024x1024"),
        ("1376x768", "1376x768"),
        ("2048x2048", "2048x2048"),
        # Junk falls back rather than sending an invalid size to the vendor.
        (None, "768x1376"),
        ("garbage", "768x1376"),
        ("0x0", "768x1376"),
    ],
)
def test_normalize_vidu_image_size(requested, expected):
    assert normalize_vidu_image_size(requested) == expected


def test_size_snapping_never_upgrades_the_billing_tier():
    """A 1:1 request must land on 1K (1024), not the pricier 2K/4K squares."""
    assert normalize_vidu_image_size("1500*1500") == "1024x1024"


# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------

def test_resolve_image_adapter_routes_by_model_id():
    default = WanxImageModel({})

    assert isinstance(resolve_image_adapter("vidu/vidu-q3-lite-image", default), ViduImageModel)
    assert isinstance(resolve_image_adapter("q3-fast", default), ViduImageModel)
    # Unknown / wan / vidu-video ids keep falling through to the default adapter.
    assert resolve_image_adapter("wan2.7-image-pro", default) is default
    assert resolve_image_adapter("vidu/viduq3-pro-video", default) is default
    assert resolve_image_adapter(None, default) is default


# ---------------------------------------------------------------------------
# Request payload
# ---------------------------------------------------------------------------

def test_t2i_payload_has_no_image_parts(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json
        return _FakeResponse(200, _ok_payload())

    monkeypatch.setenv("VIDU_API_KEY", "vda_test_key")
    monkeypatch.setattr("src.models.vidu.requests.post", fake_post)
    monkeypatch.setattr("src.models.vidu._download_vidu_image", lambda url, path: None)

    out = str(tmp_path / "shot.png")
    model = ViduImageModel({})
    result_path, elapsed = model.generate(
        prompt="a cat on a windowsill",
        output_path=out,
        model_name="vidu/vidu-q3-lite-image",
        size="1024*576",
    )

    assert result_path == out
    assert elapsed >= 0
    assert captured["url"].endswith("/open/reference2image")
    assert captured["headers"]["Authorization"] == "Token vda_test_key"

    body = captured["body"]
    assert body["model"] == "q3-lite"
    content = body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "a cat on a windowsill"}
    assert not [part for part in content if part["type"] == "image_url"]
    assert content[-1] == {"type": "output_image", "image": {"size": "1376x768"}}


def test_i2i_payload_carries_resolved_reference_urls(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["body"] = json
        return _FakeResponse(200, _ok_payload())

    monkeypatch.setenv("VIDU_API_KEY", "vda_test_key")
    monkeypatch.setattr("src.models.vidu.requests.post", fake_post)
    monkeypatch.setattr("src.models.vidu._download_vidu_image", lambda url, path: None)
    monkeypatch.setattr(
        ViduImageModel,
        "_resolve_reference",
        lambda self, ref, model_name: f"https://oss.example/{ref}",
    )

    model = ViduImageModel({})
    model.generate(
        prompt="same character, snow mountain",
        output_path=str(tmp_path / "shot.png"),
        ref_image_path="hero.png",
        ref_image_paths=["hero.png", "prop.png"],  # duplicate must collapse
        model_name="vidu/vidu-q3-fast-image",
        size="576*1024",
    )

    body = captured["body"]
    assert body["model"] == "q3-fast"
    content = body["messages"][0]["content"]
    image_parts = [part for part in content if part["type"] == "image_url"]
    assert [part["image_url"]["url"] for part in image_parts] == [
        "https://oss.example/hero.png",
        "https://oss.example/prop.png",
    ]
    assert content[-1] == {"type": "output_image", "image": {"size": "768x1376"}}


def test_missing_api_key_fails_with_actionable_message(monkeypatch, tmp_path):
    monkeypatch.delenv("VIDU_API_KEY", raising=False)
    model = ViduImageModel({})

    with pytest.raises(ValueError, match="VIDU_API_KEY"):
        model.generate(prompt="x", output_path=str(tmp_path / "x.png"))


def test_http_error_surfaces_vendor_body(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDU_API_KEY", "vda_test_key")
    monkeypatch.setattr(
        "src.models.vidu.requests.post",
        lambda *a, **k: _FakeResponse(400, {}, text='{"code":400,"reason":"CODEC"}'),
    )

    model = ViduImageModel({})
    with pytest.raises(RuntimeError, match="CODEC"):
        model.generate(prompt="x", output_path=str(tmp_path / "x.png"))


def test_empty_data_array_is_reported(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDU_API_KEY", "vda_test_key")
    monkeypatch.setattr(
        "src.models.vidu.requests.post",
        lambda *a, **k: _FakeResponse(200, {"created": "1", "data": []}),
    )

    model = ViduImageModel({})
    with pytest.raises(RuntimeError, match="No image URL"):
        model.generate(prompt="x", output_path=str(tmp_path / "x.png"))


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------

def _jpeg_bytes(size=(8, 8)):
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _png_bytes(size=(8, 8)):
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 200, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeStreamResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


def _patch_download_session(monkeypatch, content):
    """Make _download_vidu_image's requests.Session().get return fixed bytes."""

    class _FakeSession:
        def mount(self, *_args, **_kwargs):
            return None

        def get(self, *_args, **_kwargs):
            return _FakeStreamResponse(content)

    monkeypatch.setattr("src.models.vidu.requests.Session", lambda: _FakeSession())


def test_jpeg_response_is_transcoded_to_png(monkeypatch, tmp_path):
    """Vidu always answers JPEG; a .png path must contain a real PNG.

    Regression test: the first end-to-end run wrote JPEG bytes into a .png file.
    """
    from src.models.vidu import _download_vidu_image

    _patch_download_session(monkeypatch, _jpeg_bytes())
    out = tmp_path / "shot.png"
    _download_vidu_image("https://example/img", str(out))

    written = out.read_bytes()
    assert written.startswith(b"\x89PNG\r\n\x1a\n"), "a .png file must hold real PNG bytes"


def test_matching_format_is_written_untouched(monkeypatch, tmp_path):
    """No needless re-encode when the response already matches the extension."""
    from src.models.vidu import _download_vidu_image

    original = _png_bytes()
    _patch_download_session(monkeypatch, original)
    out = tmp_path / "shot.png"
    _download_vidu_image("https://example/img", str(out))

    assert out.read_bytes() == original


def test_jpg_extension_keeps_jpeg_bytes(monkeypatch, tmp_path):
    """A .jpg request must not be pointlessly transcoded."""
    from src.models.vidu import _download_vidu_image

    original = _jpeg_bytes()
    _patch_download_session(monkeypatch, original)
    out = tmp_path / "shot.jpg"
    _download_vidu_image("https://example/img", str(out))

    assert out.read_bytes() == original


def test_sniffer_identifies_formats():
    from src.models.vidu import _sniff_image_format

    assert _sniff_image_format(_png_bytes()) == "png"
    assert _sniff_image_format(_jpeg_bytes()) == "jpeg"
    assert _sniff_image_format(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert _sniff_image_format(b"not an image") == "unknown"


def test_partial_write_is_cleaned_up(monkeypatch, tmp_path):
    """A failed write must not leave a .tmp turd next to the target."""
    from src.models.vidu import _download_vidu_image

    _patch_download_session(monkeypatch, _png_bytes())

    real_open = open

    def exploding_open(path, *args, **kwargs):
        if str(path).endswith(".tmp"):
            handle = real_open(path, *args, **kwargs)
            handle.close()
            raise OSError("disk full")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", exploding_open)

    out = tmp_path / "shot.png"
    with pytest.raises(OSError):
        _download_vidu_image("https://example/img", str(out))

    monkeypatch.undo()
    assert not (tmp_path / "shot.png.tmp").exists()
