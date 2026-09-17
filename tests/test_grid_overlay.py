import io

import pytest
from PIL import Image

from src.utils.grid_overlay import apply_grid_overlay


def _make_image_bytes(fmt="PNG", size=(100, 80), color=(255, 255, 255)):
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_grid_size_zero_returns_original_bytes_unchanged():
    data = _make_image_bytes()
    result = apply_grid_overlay(data, "png", 0)
    assert result == data


def test_grid_size_4_draws_black_lines():
    data = _make_image_bytes(size=(100, 100))
    result = apply_grid_overlay(data, "png", 4)
    assert result != data
    img = Image.open(io.BytesIO(result))
    # Sample the expected vertical/horizontal grid line positions.
    for i in (1, 2, 3):
        x = round(100 * i / 4)
        assert img.getpixel((x, 50)) == (0, 0, 0)
        y = round(100 * i / 4)
        assert img.getpixel((50, y)) == (0, 0, 0)


def test_grid_size_5_draws_16_and_25_cells_respectively():
    data = _make_image_bytes(size=(100, 100))
    result = apply_grid_overlay(data, "png", 5)
    img = Image.open(io.BytesIO(result))
    for i in (1, 2, 3, 4):
        x = round(100 * i / 5)
        assert img.getpixel((x, 50)) == (0, 0, 0)


def test_invalid_grid_size_raises():
    data = _make_image_bytes()
    with pytest.raises(ValueError):
        apply_grid_overlay(data, "png", 3)


def test_jpeg_roundtrip_preserves_format():
    data = _make_image_bytes(fmt="JPEG")
    result = apply_grid_overlay(data, "jpg", 4)
    img = Image.open(io.BytesIO(result))
    assert img.format == "JPEG"


def test_unsupported_extension_raises():
    data = _make_image_bytes()
    with pytest.raises(ValueError):
        apply_grid_overlay(data, "bmp", 4)
