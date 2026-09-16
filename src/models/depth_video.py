"""Local black-and-white depth video generation (Video Depth Anything).

This is the only model in the project that runs on the user's own GPU instead
of a vendor API. It turns a reference dance clip into the temporally-consistent
grayscale depth video that drives motion replication.

Why local at all: every hosted video model we can reach refuses a photoreal
human as a reference *image* (Ark answers
``InputImageSensitiveContentDetected.PrivacyInformation``), so the motion signal
has to be stripped of identity before it leaves the machine. A depth map has no
face in it.

Weights are downloaded on first use into ``output/models/video-depth-anything``
— they are deliberately NOT bundled into the desktop build, which would add
1.4 GB to the installer.
"""

import os
import time
from typing import Callable, Dict, Optional, Tuple

from ..utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

WEIGHTS_DIR = os.path.join("output", "models", "video-depth-anything")

# repo id -> the single .pth each one publishes
ENCODERS: Dict[str, Dict] = {
    "vitl": {
        "filename": "video_depth_anything_vitl.pth",
        "repo": "depth-anything/Video-Depth-Anything-Large",
        "config": {"encoder": "vitl", "features": 256, "out_channels": [256, 512, 1024, 1024]},
        "approx_bytes": 1_538_392_012,
    },
    "vits": {
        "filename": "video_depth_anything_vits.pth",
        "repo": "depth-anything/Video-Depth-Anything-Small",
        "config": {"encoder": "vits", "features": 64, "out_channels": [48, 96, 192, 384]},
        "approx_bytes": 116_440_756,
    },
}

# hf-mirror first: from mainland China it resolves in ~1s against ~4s for the
# canonical host, and the canonical host is the one that intermittently resets.
_WEIGHT_HOSTS = ("https://hf-mirror.com", "https://huggingface.co")

DEFAULT_ENCODER = "vitl"

# Upstream's default, and the resolution the model was trained at. Going above
# it buys nothing; going below it costs surprisingly little quality (see
# auto_input_size).
MAX_INPUT_SIZE = 518
MIN_INPUT_SIZE = 210
PATCH = 14  # input_size must stay a multiple of the ViT patch size

# Peak VRAM as a function of input_size, fitted to measurements on an
# RTX 4060 Laptop (8 GB), 121 frames of 480x854. The intercept is the resident
# model plus resolution-independent activations; the quadratic term is the
# attention/patch grid.
#
#   vitl:  518 -> 10.60 GB / 720.0 s*   392 -> 7.02 GB / 51.1 s   308 -> 5.15 GB
#   vits:  518 ->  2.76 GB /  10.9 s    392 -> 1.67 GB /  5.5 s
#
#   * 518 on this card exceeds VRAM and spills to system RAM, which is why it
#     is 14x slower than 392 rather than ~1.7x.
_VRAM_FIT = {
    "vitl": (2.182, 3.139e-05),
    "vits": (0.209, 9.506e-06),
}

# Fraction of total VRAM we're willing to touch. 0.88 lands an 8 GB card on
# vitl input_size 392, which is the measured sweet spot for that encoder.
_VRAM_BUDGET = 0.88


class DepthVideoError(RuntimeError):
    """Raised for conditions the user can act on (no GPU, OOM, missing deps)."""


def auto_input_size(total_vram_gb: Optional[float], encoder: str = DEFAULT_ENCODER) -> int:
    """Largest input_size for ``encoder`` whose predicted peak fits the card.

    This exists because a fixed default is actively harmful on consumer cards.
    On Windows, exceeding VRAM does not raise — WDDM silently spills the
    overflow into system RAM, so the run still "works" while getting an order
    of magnitude slower. Measured on the 8 GB reference card, 24-frame clip,
    vitl: 518 -> 241.7 s (10.6 GB, spilling); 392 -> 15.3 s (7.0 GB, resident);
    308 -> 4.7 s (5.2 GB).

    Quality from 518 down to 392 is near-indistinguishable; 308 visibly softens
    limb edges. So the right answer is "the biggest thing that still fits".
    """
    base, per_px2 = _VRAM_FIT[encoder]
    if not total_vram_gb:
        # CPU path: nothing fits well and everything is slow, so bias small.
        return MIN_INPUT_SIZE

    budget = total_vram_gb * _VRAM_BUDGET
    if budget <= base:
        return MIN_INPUT_SIZE

    raw = ((budget - base) / per_px2) ** 0.5
    size = int(raw // PATCH) * PATCH  # round DOWN — overshooting is the failure
    return max(MIN_INPUT_SIZE, min(MAX_INPUT_SIZE, size))


def auto_plan(total_vram_gb: Optional[float]) -> Tuple[str, int]:
    """Pick (encoder, input_size) for this machine.

    Prefer the large encoder only when the card can run it at full resolution.
    Below that, a *small* encoder at full resolution beats a *large* one that
    had to be downscaled: side by side on the reference clip, vits@518 and
    vitl@392 are visually equivalent on the subject silhouette, but vits@518
    takes 10.9 s against 51.1 s and 2.76 GB against 7.02 GB.

    In other words, for this use — producing a motion signal, not a
    measurement — input resolution matters more than encoder capacity.
    """
    if auto_input_size(total_vram_gb, "vitl") >= MAX_INPUT_SIZE:
        return "vitl", MAX_INPUT_SIZE
    return "vits", auto_input_size(total_vram_gb, "vits")


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

def weight_path(encoder: str = DEFAULT_ENCODER) -> str:
    return os.path.join(WEIGHTS_DIR, ENCODERS[encoder]["filename"])


def weights_present(encoder: str = DEFAULT_ENCODER) -> bool:
    """A weight file counts as present only at roughly its published size.

    A half-finished download is the common failure here, and torch's error for
    a truncated archive ("central directory not found") tells the user nothing
    about what to do, so check the size up front instead.
    """
    path = weight_path(encoder)
    if not os.path.exists(path):
        return False
    expected = ENCODERS[encoder]["approx_bytes"]
    return os.path.getsize(path) >= expected * 0.98


def download_weights(
    encoder: str = DEFAULT_ENCODER,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> str:
    """Fetch the checkpoint if it isn't already on disk. Returns its path."""
    import requests

    dest = weight_path(encoder)
    if weights_present(encoder):
        return dest

    spec = ENCODERS[encoder]
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    tmp = dest + ".part"
    last_error: Optional[Exception] = None

    for host in _WEIGHT_HOSTS:
        url = f"{host}/{spec['repo']}/resolve/main/{spec['filename']}"
        try:
            logger.info("Downloading depth weights: %s", url)
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or spec["approx_bytes"])
                done = 0
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        done += len(chunk)
                        if progress_cb:
                            progress_cb(done / total, f"下载深度模型权重 {done / 2**20:.0f}/{total / 2**20:.0f} MB")
            os.replace(tmp, dest)
            return dest
        except Exception as exc:  # try the next host before giving up
            last_error = exc
            logger.warning("Weight download from %s failed: %s", host, exc)
            if os.path.exists(tmp):
                os.remove(tmp)

    raise DepthVideoError(
        f"无法下载深度模型权重（{spec['filename']}）。最后一个错误：{last_error}. "
        f"也可以手动下载后放到 {dest}"
    )


# ---------------------------------------------------------------------------
# Video IO — cv2 rather than decord/imageio
# ---------------------------------------------------------------------------

def _read_frames(path: str, max_seconds: Optional[float], target_fps: Optional[float],
                 max_res: int) -> Tuple["np.ndarray", float]:  # noqa: F821
    """Decode to an (N, H, W, 3) RGB uint8 array plus the fps to render at.

    cv2 rather than the upstream decord path: decord wheels are unmaintained and
    break on several Python/OS combinations we ship to, and cv2 is already a
    hard dependency here.
    """
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise DepthVideoError(f"无法打开视频：{path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    out_fps = float(target_fps) if target_fps else float(src_fps)
    # Keep every Nth frame when downsampling fps. Sampling beats re-timing here
    # because the depth model consumes a frame sequence, not a timeline.
    step = max(1, int(round(src_fps / out_fps))) if target_fps else 1
    limit = int(max_seconds * src_fps) if max_seconds else None

    frames = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if limit is not None and idx >= limit:
            break
        if idx % step == 0:
            h, w = frame.shape[:2]
            if max(h, w) > max_res:
                scale = max_res / max(h, w)
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)),
                                   interpolation=cv2.INTER_AREA)
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        idx += 1
    cap.release()

    if not frames:
        raise DepthVideoError(f"视频里没有解出任何帧：{path}")
    return np.asarray(frames), src_fps / step


def _write_gray_video(depths, out_path: str, fps: float, contrast: str) -> None:
    """Render the depth array as an 8-bit grayscale mp4.

    Normalisation is computed over the WHOLE clip, never per frame. Per-frame
    min/max would re-map the grey levels every frame, so a subject holding
    still would visibly pulse — reintroducing exactly the flicker this model
    exists to avoid.
    """
    import cv2
    import numpy as np

    d = np.asarray(depths, dtype=np.float32)

    if contrast == "raw":
        lo, hi = float(d.min()), float(d.max())
    else:
        # Percentile clipping. The floor nearest the camera and the wall
        # furthest from it own both extremes of the raw range, which squeezes
        # the subject into a narrow band of greys and flattens their limbs into
        # a single flat silhouette. Clipping the outer 2% spends the range on
        # the subject instead.
        lo, hi = np.percentile(d, 2.0), np.percentile(d, 98.0)

    gray = np.clip((d - lo) / max(hi - lo, 1e-8), 0.0, 1.0)
    gray = (gray * 255.0).astype(np.uint8)

    h, w = gray.shape[1], gray.shape[2]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    if _write_h264(gray, out_path, fps, w, h):
        return

    # No ffmpeg on this machine. cv2's mp4v is MPEG-4 Part 2, which no browser
    # decodes, so the clip still drives the video model but its <video> preview
    # stays a black player — better than failing the whole job.
    logger.warning(
        "ffmpeg unavailable; writing %s as mp4v — it will not preview in a browser",
        out_path,
    )
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not writer.isOpened():
        raise DepthVideoError(f"无法写出视频：{out_path}")
    for frame in gray:
        writer.write(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
    writer.release()


def _write_h264(gray, out_path: str, fps: float, w: int, h: int) -> bool:
    """Pipe the grayscale frames straight into ffmpeg as H.264. False if ffmpeg is missing.

    Piping rather than transcoding a cv2 file: it avoids a second lossy pass
    over a depth map whose grey levels *are* the signal the video model reads.
    """
    import subprocess

    from ..utils.system_check import get_ffmpeg_path

    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return False

    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "gray",
        "-s", f"{w}x{h}", "-r", f"{fps:.6f}",
        "-i", "-",
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        # yuv420p + even dimensions: the combination every browser and every
        # vendor video API accepts. An odd dimension makes libx264 bail.
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
        "-movflags", "+faststart",
        out_path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in gray:
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
    except (BrokenPipeError, OSError) as exc:
        proc.kill()
        raise DepthVideoError(f"ffmpeg 写视频失败：{exc}") from exc

    _, stderr = proc.communicate(timeout=300)
    if proc.returncode != 0 or not os.path.exists(out_path):
        raise DepthVideoError(f"ffmpeg 写视频失败：{stderr.decode('utf-8', 'replace')[:300]}")
    return True


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class DepthVideoModel:
    """Video Depth Anything, loaded lazily and cached per encoder."""

    _cache: Dict[str, object] = {}

    def __init__(self, encoder: str = "auto"):
        if encoder == "auto":
            report = self.device_report()
            encoder = report.get("recommended_encoder") or DEFAULT_ENCODER
        if encoder not in ENCODERS:
            raise ValueError(f"Unknown depth encoder {encoder!r}; expected one of {list(ENCODERS)}")
        self.encoder = encoder

    # -- capability ------------------------------------------------------

    @staticmethod
    def device_report() -> Dict:
        """What the machine can actually do, for the UI to show before a run."""
        try:
            import torch
        except ImportError:
            return {"available": False, "reason": "torch 未安装"}

        if not torch.cuda.is_available():
            return {
                "available": True, "device": "cpu", "vram_gb": None,
                "recommended_encoder": "vits",
                "recommended_input_size": MIN_INPUT_SIZE,
                "warning": "没有检测到可用的 CUDA 显卡，深度推理会走 CPU，慢到不可用。",
            }
        props = torch.cuda.get_device_properties(0)
        vram_gb = round(props.total_memory / 2**30, 2)
        encoder, input_size = auto_plan(vram_gb)
        return {
            "available": True,
            "device": "cuda",
            "gpu_name": props.name,
            "vram_gb": vram_gb,
            "recommended_encoder": encoder,
            "recommended_input_size": input_size,
        }

    # -- loading ---------------------------------------------------------

    def _load(self):
        if self.encoder in self._cache:
            return self._cache[self.encoder]

        import torch
        from ..vendor.video_depth_anything.video_depth import VideoDepthAnything

        ckpt = download_weights(self.encoder)
        spec = ENCODERS[self.encoder]

        model = VideoDepthAnything(**spec["config"], metric=False)
        model.load_state_dict(torch.load(ckpt, map_location="cpu"), strict=True)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device).eval()

        self._cache[self.encoder] = (model, device)
        logger.info("Loaded Video-Depth-Anything %s on %s", self.encoder, device)
        return self._cache[self.encoder]

    @classmethod
    def unload(cls) -> None:
        """Drop the cached model and free its VRAM.

        Worth calling between a depth run and a vendor call in the same
        session: the large encoder sits on ~1.4 GB even when idle, and on an
        8 GB card that is the difference between the next run fitting or not.
        """
        cls._cache.clear()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    # -- inference -------------------------------------------------------

    def generate(
        self,
        input_video: str,
        output_path: str,
        *,
        input_size: Optional[int] = None,
        max_seconds: Optional[float] = None,
        target_fps: Optional[float] = None,
        max_res: int = 1280,
        contrast: str = "percentile",
        save_npz: bool = False,
        progress_cb: Optional[Callable[[float, str], None]] = None,
    ) -> Dict:
        """Run depth estimation over ``input_video`` and write a grayscale mp4.

        ``input_size`` defaults to whatever fits this machine's VRAM — see
        ``auto_input_size``. Pass an explicit value only to override that.

        Returns timing/shape metadata the UI shows next to the result.
        """
        import numpy as np
        import torch

        if not os.path.exists(input_video):
            raise DepthVideoError(f"找不到输入视频：{input_video}")

        if progress_cb:
            progress_cb(0.0, "准备深度模型")
        model, device = self._load()

        if input_size is None:
            vram = (torch.cuda.get_device_properties(0).total_memory / 2**30
                    if device == "cuda" else None)
            input_size = auto_input_size(vram, self.encoder)
            logger.info("Depth input_size auto-selected: %d (%s, vram=%s)",
                        input_size, self.encoder, vram)

        frames, fps = _read_frames(input_video, max_seconds, target_fps, max_res)
        if progress_cb:
            progress_cb(0.1, f"已解出 {len(frames)} 帧，开始推理")

        started = time.time()
        if device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        try:
            depths, _ = model.infer_video_depth(
                frames, fps, input_size=input_size, device=device, fp32=False
            )
        except torch.OutOfMemoryError as exc:
            raise DepthVideoError(
                f"显存不足（{exc}）。可以调小 input_size（当前 {input_size}，"
                f"依次试 392 / 308）、降低 target_fps，或改用 vits 小模型。"
            ) from exc
        elapsed = time.time() - started

        peak_vram = (torch.cuda.max_memory_allocated() / 2**30) if device == "cuda" else None

        if progress_cb:
            progress_cb(0.9, "写出深度视频")
        _write_gray_video(depths, output_path, fps, contrast)

        npz_path = None
        if save_npz:
            npz_path = os.path.splitext(output_path)[0] + ".npz"
            np.savez_compressed(npz_path, depths=np.asarray(depths), fps=fps)

        if progress_cb:
            progress_cb(1.0, "深度视频完成")

        return {
            "output_path": output_path,
            "npz_path": npz_path,
            "encoder": self.encoder,
            "device": device,
            "frames": int(len(frames)),
            "fps": float(fps),
            "width": int(frames.shape[2]),
            "height": int(frames.shape[1]),
            "input_size": input_size,
            "elapsed_sec": round(elapsed, 1),
            "peak_vram_gb": round(peak_vram, 2) if peak_vram else None,
        }
