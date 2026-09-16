"""Media paths returned by the playground API must be '/'-separated.

The frontend turns a stored path into a URL by stripping an ``output/`` prefix
and appending the rest to ``/files/``. ``os.path.join`` yields
``output\\playground\\uploads\\x.png`` on Windows, the prefix strip misses, and
the browser ends up requesting ``/files/output/playground/...`` — a 404, which
renders as a broken image. Every path leaving the backend is normalized.
"""

import io
import os

import pytest
from fastapi import UploadFile

from src.apps.playground import api as playground_api
from src.utils.media_refs import to_posix_media_path

BACKSLASH = chr(92)

PNG_BYTES = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 32
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def test_to_posix_media_path_normalizes_windows_separators():
    raw = BACKSLASH.join(["output", "playground", "uploads", "x.png"])
    assert to_posix_media_path(raw) == "output/playground/uploads/x.png"


def test_to_posix_media_path_leaves_posix_paths_untouched():
    assert to_posix_media_path("output/playground/images/a.png") == "output/playground/images/a.png"


def test_upload_media_returns_posix_path(tmp_path, monkeypatch):
    monkeypatch.setattr(playground_api, "UPLOAD_DIR", os.path.join(str(tmp_path), "uploads"))
    upload = UploadFile(filename="portrait.png", file=io.BytesIO(PNG_BYTES))

    result = playground_api.upload_media(upload)

    assert BACKSLASH not in result["path"]
    assert result["path"].endswith(".png")


def test_upload_video_returns_posix_path(tmp_path, monkeypatch):
    monkeypatch.setattr(playground_api, "UPLOAD_DIR", os.path.join(str(tmp_path), "uploads"))
    upload = UploadFile(filename="dance.mp4", file=io.BytesIO(MP4_BYTES))

    result = playground_api.upload_video(upload, _user=None)

    assert BACKSLASH not in result["path"]
    assert result["path"].endswith(".mp4")
