"""Optional grid-line overlay for uploaded reference photos.

Burns a fixed 6x6, 10px-wide grid permanently into an uploaded image, to
help downstream AI models read proportions/composition (e.g. character pose
or face-swap reference photos). This is opt-in per upload (grid_size=0
leaves the image untouched) and, once applied, is not reversible — the
caller is responsible for keeping their own original if they need it later.
"""

import io

from PIL import Image, ImageDraw

ALLOWED_GRID_SIZES = (0, 6)
GRID_LINE_WIDTH = 10
_COLOR_RGB = {"black": (0, 0, 0), "white": (255, 255, 255)}

_PIL_FORMAT_BY_EXT = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "gif": "GIF",
    "webp": "WEBP",
}


def apply_grid_overlay(image_bytes: bytes, ext: str, grid_size: int, color: str = "black") -> bytes:
    """Return *image_bytes* with an evenly-spaced grid_size x grid_size grid burned in.

    grid_size=0 is a no-op passthrough (returns image_bytes unchanged) so
    callers can route the "original photo" choice through the same
    function without a separate branch. color is "black" or "white".
    """
    if grid_size == 0:
        return image_bytes
    if grid_size not in ALLOWED_GRID_SIZES:
        raise ValueError(f"grid_size must be one of {ALLOWED_GRID_SIZES}, got {grid_size}")
    if color not in _COLOR_RGB:
        raise ValueError(f"color must be one of {tuple(_COLOR_RGB)}, got {color!r}")

    fmt = _PIL_FORMAT_BY_EXT.get(ext.lower())
    if fmt is None:
        raise ValueError(f"Unsupported image extension for grid overlay: {ext!r}")

    with Image.open(io.BytesIO(image_bytes)) as img:
        img.load()
        # JPEG has no alpha channel; convert paletted/alpha modes so the
        # overlay draws predictably and re-encoding doesn't choke on
        # save(format="JPEG") receiving an "RGBA"/"P" image.
        if fmt == "JPEG" and img.mode != "RGB":
            img = img.convert("RGB")

        rgb = _COLOR_RGB[color]
        width, height = img.size
        draw = ImageDraw.Draw(img)
        for i in range(1, grid_size):
            x = round(width * i / grid_size)
            draw.line([(x, 0), (x, height)], fill=rgb, width=GRID_LINE_WIDTH)
            y = round(height * i / grid_size)
            draw.line([(0, y), (width, y)], fill=rgb, width=GRID_LINE_WIDTH)

        out = io.BytesIO()
        save_kwargs = {"quality": 95} if fmt == "JPEG" else {}
        img.save(out, format=fmt, **save_kwargs)
        return out.getvalue()
