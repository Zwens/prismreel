"""Tests for the local depth-video step of the dance-swap flow.

The interesting logic here is hardware sizing, not inference: picking an
input_size that fits the card is the difference between 10 seconds and 12
minutes of wall clock, because Windows spills past-VRAM allocations into system
RAM instead of raising (measured: vitl@518 needs 10.6 GB and runs ~16x slower
than vitl@392 on an 8 GB card).

These tests deliberately avoid importing torch: the module defers every heavy
import into the functions that need it, so a machine without a CUDA build can
still load the API that exposes this.
"""
import io

import pytest
from fastapi import HTTPException


# ── VRAM-aware sizing ───────────────────────────────────────────────────

class TestAutoInputSize:
    def test_size_grows_with_available_vram(self):
        from src.models.depth_video import auto_input_size

        sizes = [auto_input_size(v, "vitl") for v in (4, 6, 8, 12, 24)]
        assert sizes == sorted(sizes)

    def test_size_is_always_a_multiple_of_the_patch_size(self):
        from src.models.depth_video import auto_input_size, PATCH

        for vram in (3, 4, 5, 6, 8, 10, 12, 16, 24, 48):
            assert auto_input_size(vram, "vitl") % PATCH == 0
            assert auto_input_size(vram, "vits") % PATCH == 0

    def test_size_never_exceeds_the_trained_resolution(self):
        from src.models.depth_video import auto_input_size, MAX_INPUT_SIZE

        assert auto_input_size(80, "vitl") == MAX_INPUT_SIZE
        assert auto_input_size(80, "vits") == MAX_INPUT_SIZE

    def test_a_tiny_card_still_gets_a_usable_floor(self):
        from src.models.depth_video import auto_input_size, MIN_INPUT_SIZE

        assert auto_input_size(1, "vitl") == MIN_INPUT_SIZE

    def test_cpu_biases_small(self):
        from src.models.depth_video import auto_input_size, MIN_INPUT_SIZE

        assert auto_input_size(None, "vitl") == MIN_INPUT_SIZE

    def test_the_chosen_size_fits_the_budget_it_was_given(self):
        """The fit is the whole point — a size whose predicted peak exceeds the
        budget would reintroduce the spill this function exists to avoid."""
        from src.models.depth_video import auto_input_size, _VRAM_FIT, _VRAM_BUDGET

        for encoder in ("vitl", "vits"):
            base, per_px2 = _VRAM_FIT[encoder]
            for vram in (6, 8, 12, 16):
                size = auto_input_size(vram, encoder)
                predicted = base + per_px2 * size * size
                # The floor is allowed to exceed a very small budget; anything
                # the formula actually chose must fit.
                if size > 210:
                    assert predicted <= vram * _VRAM_BUDGET

    def test_the_fit_reproduces_the_measurements_it_came_from(self):
        from src.models.depth_video import _VRAM_FIT

        base, per_px2 = _VRAM_FIT["vitl"]
        for size, measured in ((518, 10.60), (392, 7.02), (308, 5.15)):
            assert base + per_px2 * size * size == pytest.approx(measured, abs=0.05)

        base, per_px2 = _VRAM_FIT["vits"]
        for size, measured in ((518, 2.76), (392, 1.67)):
            assert base + per_px2 * size * size == pytest.approx(measured, abs=0.05)


class TestAutoPlan:
    def test_a_small_card_gets_the_small_encoder_at_full_resolution(self):
        """Measured: vits@518 and vitl@392 look equivalent on the subject, but
        vits@518 is 10.9s against 51.1s. Resolution beats encoder capacity for
        a motion signal, so never downscale the large one to make it fit."""
        from src.models.depth_video import auto_plan, MAX_INPUT_SIZE

        encoder, size = auto_plan(8.0)
        assert encoder == "vits"
        assert size == MAX_INPUT_SIZE

    def test_a_large_card_gets_the_large_encoder(self):
        from src.models.depth_video import auto_plan, MAX_INPUT_SIZE

        assert auto_plan(24.0) == ("vitl", MAX_INPUT_SIZE)

    def test_cpu_falls_back_to_the_small_encoder(self):
        from src.models.depth_video import auto_plan

        encoder, _ = auto_plan(None)
        assert encoder == "vits"


class TestWeightBookkeeping:
    def test_a_truncated_download_does_not_count_as_present(self, tmp_path, monkeypatch):
        """torch's error for a half-downloaded archive says nothing actionable,
        so size is checked before it ever gets that far."""
        from src.models import depth_video

        monkeypatch.setattr(depth_video, "WEIGHTS_DIR", str(tmp_path))
        path = tmp_path / depth_video.ENCODERS["vits"]["filename"]
        path.write_bytes(b"\x00" * 1024)

        assert depth_video.weights_present("vits") is False

    def test_a_complete_download_counts_as_present(self, tmp_path, monkeypatch):
        from src.models import depth_video

        monkeypatch.setattr(depth_video, "WEIGHTS_DIR", str(tmp_path))
        spec = depth_video.ENCODERS["vits"]
        path = tmp_path / spec["filename"]
        path.write_bytes(b"\x00" * spec["approx_bytes"])

        assert depth_video.weights_present("vits") is True


# ── Video upload sniffing ───────────────────────────────────────────────

class _FakeUpload:
    """Minimal stand-in for fastapi.UploadFile — only .file is read."""

    def __init__(self, data: bytes):
        self.file = io.BytesIO(data)


def _mp4_bytes(payload: bytes = b"") -> bytes:
    return b"\x00\x00\x00\x20" + b"ftyp" + b"isom" + b"\x00" * 16 + payload


class TestVideoUpload:
    def test_an_mp4_is_accepted_and_named_by_its_content(self, tmp_path):
        from src.utils.upload_guard import save_video_upload

        dest = save_video_upload(_FakeUpload(_mp4_bytes()), str(tmp_path / "clip"))

        assert dest.endswith(".mp4")
        assert (tmp_path / "clip.mp4").exists()

    def test_a_quicktime_brand_is_named_mov(self, tmp_path):
        from src.utils.upload_guard import save_video_upload

        data = b"\x00\x00\x00\x20" + b"ftyp" + b"qt  " + b"\x00" * 16
        dest = save_video_upload(_FakeUpload(data), str(tmp_path / "clip"))

        assert dest.endswith(".mov")

    def test_a_webm_is_accepted(self, tmp_path):
        from src.utils.upload_guard import save_video_upload

        data = b"\x1a\x45\xdf\xa3" + b"\x00" * 28
        dest = save_video_upload(_FakeUpload(data), str(tmp_path / "clip"))

        assert dest.endswith(".webm")

    def test_an_image_masquerading_as_a_video_is_rejected(self, tmp_path):
        from src.utils.upload_guard import save_video_upload

        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
        with pytest.raises(HTTPException) as exc:
            save_video_upload(_FakeUpload(png), str(tmp_path / "clip"))

        assert exc.value.status_code == 400

    def test_an_oversized_upload_is_rejected_and_leaves_nothing_behind(self, tmp_path, monkeypatch):
        """A partial file left on disk would be picked up by the pipeline later
        and fail somewhere far less obvious than the upload itself."""
        from src.utils import upload_guard

        monkeypatch.setattr(upload_guard, "MAX_VIDEO_UPLOAD_BYTES", 1024)
        data = _mp4_bytes(b"\x00" * 4096)

        with pytest.raises(HTTPException) as exc:
            upload_guard.save_video_upload(_FakeUpload(data), str(tmp_path / "clip"))

        assert exc.value.status_code == 413
        assert list(tmp_path.iterdir()) == []

    def test_a_truncated_header_is_rejected_rather_than_guessed(self, tmp_path):
        from src.utils.upload_guard import save_video_upload

        with pytest.raises(HTTPException):
            save_video_upload(_FakeUpload(b"\x00\x00\x00"), str(tmp_path / "clip"))


# ── Output encoding ─────────────────────────────────────────────────────

def _probe_codec(path: str) -> str:
    import json
    import os
    import shutil
    import subprocess

    from src.utils.system_check import get_ffmpeg_path

    ffmpeg = get_ffmpeg_path()
    # Only the basename may be rewritten: the install directory itself is
    # named 'ffmpeg-8.1.1-full_build' on this machine.
    ffprobe = shutil.which("ffprobe")
    if not ffprobe and ffmpeg:
        head, tail = os.path.split(ffmpeg)
        ffprobe = os.path.join(head, tail.replace("ffmpeg", "ffprobe"))
    if not ffprobe:
        pytest.skip("ffprobe not available")
    out = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name", "-of", "json", path],
        capture_output=True, text=True, timeout=30,
    )
    return json.loads(out.stdout)["streams"][0]["codec_name"]


class TestDepthClipEncoding:
    """The depth clip is previewed in a <video> tag before it is ever fed to a
    model, and browsers decode none of cv2's default MPEG-4 Part 2 output — it
    renders as a black player stuck at 0:00. H.264 is the only codec every
    target browser accepts."""

    def _gray_clip(self):
        np = pytest.importorskip("numpy")
        pytest.importorskip("cv2")
        # 8 frames of a moving bright block, even dimensions.
        clip = np.zeros((8, 64, 48), dtype=np.float32)
        for i in range(8):
            clip[i, i * 4 : i * 4 + 16, 8:40] = 1.0
        return clip

    def test_depth_clip_is_written_as_h264(self, tmp_path):
        from src.models.depth_video import _write_gray_video

        out = str(tmp_path / "depth.mp4")
        _write_gray_video(self._gray_clip(), out, 12.0, "raw")

        assert _probe_codec(out) == "h264"

    def test_depth_clip_keeps_every_frame(self, tmp_path):
        from src.models.depth_video import _write_gray_video

        out = str(tmp_path / "depth.mp4")
        _write_gray_video(self._gray_clip(), out, 12.0, "raw")

        import cv2

        cap = cv2.VideoCapture(out)
        count = 0
        while cap.read()[0]:
            count += 1
        cap.release()
        assert count == 8
