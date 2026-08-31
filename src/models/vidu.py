"""Vidu video generation model adapter.

API: https://api.vidu.cn/ent/v2
Auth: Token header using VIDU_API_KEY
Models: viduq3-pro (default), viduq3-turbo (fast), viduq3-drama (reference-to-video)

Endpoints by mode:
  t2v -> /text2video
  i2v -> /img2video
  r2v -> /reference2video   (docs/api-reference/vidu-reference2video.md)
"""

import logging
import os
import time
from typing import Dict, Any, List, Optional, Sequence, Tuple

import requests

from .base import VideoGenModel
from .image import ImageGenModel
from ..utils.endpoints import get_provider_base_url
from ..utils.oss_utils import OSSImageUploader
from ..utils.provider_media import resolve_media_input

logger = logging.getLogger(__name__)
DEFAULT_T2V_MODEL = "viduq3-pro"
DEFAULT_I2V_MODEL = "viduq3-pro"
DEFAULT_R2V_MODEL = "viduq3-drama"

# Catalog ids carry a family prefix and a mode suffix (vidu/viduq3-pro-video,
# viduq3-pro-i2v, viduq3-drama-r2v). The vendor API only accepts the bare model
# name — it rejects anything else with FieldInvalid "model is not supported".
_VENDOR_MODEL_PREFIX = "vidu/"
_VENDOR_MODEL_SUFFIXES = ("-i2v", "-r2v", "-t2v", "-video")


# Models the vendor /reference2video endpoint accepts, per the Vidu 参考生 API
# (Q3) doc, rev. 2026-08-24. Note the absence of viduq3-pro: it is an
# i2v/t2v-only line, so stripping the mode suffix off viduq3-pro-r2v yields a
# name this endpoint rejects with FieldInvalid "model is not supported".
VENDOR_R2V_MODELS = frozenset({
    "viduq3-drama",
    "viduq3-ad",
    "viduq3-mix",
    "viduq3-turbo",
    "viduq3",
    "viduq2-pro",
    "viduq2",
    "viduq1",
    "vidu2.0",
})

_catalog_accessor = None


def _get_catalog():
    """Lazily load the model catalog; None when it is unavailable."""
    global _catalog_accessor
    if _catalog_accessor is None:
        try:
            from ..utils.model_catalog import get_catalog_accessor
            _catalog_accessor = get_catalog_accessor()
        except Exception as e:  # pragma: no cover - catalog is optional at runtime
            logger.debug("Failed to load model catalog: %s", e)
            _catalog_accessor = False
    return _catalog_accessor if _catalog_accessor is not False else None


def resolve_r2v_vendor_model(model_name: Optional[str]) -> str:
    """Resolve a catalog r2v id to the model name /reference2video accepts.

    Prefers the catalog's vendor-side api_model_id, because the r2v line does
    not mirror the i2v one: viduq3-pro-r2v is served by viduq3-mix, not by a
    (non-existent) viduq3-pro r2v model. Falls back to suffix stripping for
    ids the catalog does not carry.
    """
    catalog = _get_catalog()
    if catalog is not None and model_name:
        try:
            # Accept both id forms: legacy flat (viduq3-pro-r2v), which is what
            # VideoTask.model carries, and canonical mode
            # (vidu/viduq3-pro-video#r2v), which the catalog's own defaults use.
            canonical = catalog.resolve_legacy_to_canonical(model_name) or model_name
            runtime = catalog.get_mode_runtime(canonical) or {}
            api_model = (runtime.get("vendor") or {}).get("api_model_id")
            if api_model:
                return api_model
        except Exception as e:  # pragma: no cover - never block a submit on this
            logger.debug("Catalog r2v lookup failed for %s: %s", model_name, e)
    return to_vendor_model(model_name, DEFAULT_R2V_MODEL)


def to_vendor_model(model_name: Optional[str], default: str) -> str:
    """Normalize a catalog model id into the bare name the Vidu API expects.

    vidu/viduq3-pro-video -> viduq3-pro
    viduq3-drama-r2v      -> viduq3-drama
    viduq3-drama          -> viduq3-drama (unchanged)
    """
    if not model_name:
        return default
    name = model_name.strip().lower()
    if name.startswith(_VENDOR_MODEL_PREFIX):
        name = name[len(_VENDOR_MODEL_PREFIX):]
    for suffix in _VENDOR_MODEL_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name or default


class ViduModel(VideoGenModel):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key") or os.getenv("VIDU_API_KEY", "")
        self.model_name = config.get("params", {}).get("model_name", DEFAULT_I2V_MODEL)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _map_status(raw_state: str) -> str:
        """Map Vidu API states to normalized statuses."""
        mapping = {
            "created": "pending",
            "queueing": "pending",
            "processing": "running",
            "success": "succeeded",
            "failed": "failed",
        }
        return mapping.get(raw_state.lower(), "pending")

    def _resolve_vendor_image_input(
        self,
        *,
        img_url: str = None,
        img_path: str = None,
        model_name: str = None,
    ) -> str:
        """
        Resolve Vidu vendor image input via the shared provider-media layer.

        Prefer an existing remote URL when available. For local files, require an
        OSS-backed signed URL and fail clearly if the current environment cannot
        provide one.
        """
        if isinstance(img_url, str) and img_url.startswith(("http://", "https://")):
            image_ref = img_url
        else:
            image_ref = img_path or img_url

        if not image_ref:
            raise ValueError("Vidu image input requires img_path or img_url")

        resolved = resolve_media_input(
            image_ref,
            model_name=model_name or self.model_name,
            modality="image",
            backend="vendor",
            uploader=OSSImageUploader(),
        )
        return resolved.value

    def _resolve_vendor_reference_images(
        self,
        refs: Sequence[str],
        *,
        model_name: str = None,
    ) -> List[str]:
        """Resolve every R2V reference into a vendor-reachable URL.

        Vidu's reference2video only accepts public URLs, so local paths must go
        through OSS. resolve_media_input raises with an actionable message when
        OSS is not configured.
        """
        resolved: List[str] = []
        for ref in refs:
            if not ref:
                continue
            resolved.append(
                self._resolve_vendor_image_input(img_url=ref, model_name=model_name)
            )
        if not resolved:
            raise ValueError("Vidu r2v requires at least one reference image")
        return resolved

    def generate(self, prompt: str, output_path: str, img_url: str = None,
                 img_path: str = None, **kwargs) -> Tuple[str, float]:
        """Generate video using Vidu API (T2V, I2V or R2V)."""
        duration = kwargs.get("duration", 5)
        resolution = (kwargs.get("resolution") or "720p").lower()
        # No fallback to 16:9 here: leaving it unset lets each model apply its
        # own default (viduq3-drama defaults to 9:16, which is what short-form
        # drama wants). Only t2v needs an explicit default.
        aspect_ratio = kwargs.get("aspect_ratio")

        start_time = time.time()

        ref_image_urls = kwargs.get("ref_image_urls") or []
        is_r2v = (kwargs.get("generation_mode") or "").lower() == "r2v" or bool(ref_image_urls)
        is_i2v = not is_r2v and bool(img_url or img_path)
        base_url = get_provider_base_url("VIDU")

        if is_r2v:
            task_id, used_model = self._submit_r2v(
                prompt=prompt,
                image_urls=self._resolve_vendor_reference_images(
                    ref_image_urls,
                    model_name=kwargs.get("model"),
                ),
                model=kwargs.get("model"),
                duration=duration,
                resolution=resolution,
                aspect_ratio=aspect_ratio,
                seed=kwargs.get("seed", 0),
                watermark=bool(kwargs.get("watermark", False)),
                off_peak=bool(kwargs.get("off_peak", False)),
                payload=kwargs.get("payload"),
            )
        elif is_i2v:
            task_id, used_model = self._submit_i2v(
                prompt=prompt,
                image_url=self._resolve_vendor_image_input(
                    img_url=img_url,
                    img_path=img_path,
                    model_name=kwargs.get("model"),
                ),
                model=kwargs.get("model"),
                duration=duration,
                resolution=resolution,
                seed=kwargs.get("seed", 0),
                movement_amplitude=kwargs.get("movement_amplitude", "auto"),
                audio=kwargs.get("audio", True),
            )
        else:
            task_id, used_model = self._submit_t2v(
                prompt=prompt,
                model=kwargs.get("model"),
                duration=duration,
                resolution=resolution,
                aspect_ratio=aspect_ratio or "16:9",
                seed=kwargs.get("seed", 0),
                style=kwargs.get("style", "general"),
                bgm=kwargs.get("bgm", True),
            )

        logger.info(f"[Vidu] Task submitted: {task_id} (model={used_model})")

        # Poll for completion
        poll_url = f"{base_url}/tasks/{task_id}/creations"
        max_wait = 600
        poll_interval = 10
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            # The task is already submitted and billed at this point, so a
            # transient network blip must not throw away the result — keep
            # polling until max_wait instead of propagating the error.
            try:
                resp = requests.get(poll_url, headers=self._headers(), timeout=30)
            except requests.RequestException as exc:
                logger.warning(f"[Vidu] Poll request failed ({exc}); retrying (task {task_id})")
                continue

            if resp.status_code not in (200, 201):
                logger.warning(f"[Vidu] Poll returned HTTP {resp.status_code}")
                continue

            data = resp.json()
            state = data.get("state", "unknown")
            normalized = self._map_status(state)
            logger.info(f"[Vidu] Task status: {state} -> {normalized} ({elapsed}s)")

            if normalized == "succeeded":
                video_url = data["creations"][0]["url"]
                # Download video
                video_content = requests.get(video_url, timeout=120).content
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(video_content)

                generation_time = time.time() - start_time
                logger.info(f"[Vidu] Done in {generation_time:.1f}s -> {output_path}")
                return output_path, generation_time

            elif normalized == "failed":
                raise RuntimeError(f"Vidu task failed: {data}")

        raise RuntimeError(f"Vidu task timed out after {max_wait}s")

    def _submit_t2v(self, *, prompt: str, model: str = None, duration: int = 5,
                    resolution: str = "720p", aspect_ratio: str = "16:9",
                    seed: int = 0, style: str = "general", bgm: bool = True,
                    ) -> Tuple[str, str]:
        """Submit a text-to-video task. Returns (task_id, model_used)."""
        used_model = to_vendor_model(model, DEFAULT_T2V_MODEL)

        body: Dict[str, Any] = {
            "model": used_model,
            "prompt": prompt,
            "duration": duration,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "seed": seed,
            "style": style,
            "bgm": bgm,
        }

        submit_url = f"{get_provider_base_url('VIDU')}/text2video"
        logger.info(f"[Vidu] Submitting t2v task (model={used_model}, duration={duration}s)")

        resp = requests.post(submit_url, headers=self._headers(), json=body, timeout=30)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Vidu t2v submission failed (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        task_id = data.get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in Vidu response: {data}")

        return task_id, used_model

    def _submit_i2v(self, *, prompt: str, image_url: str, model: str = None,
                    duration: int = 5, resolution: str = "720p",
                    seed: int = 0, movement_amplitude: str = "auto", audio: bool = True,
                    ) -> Tuple[str, str]:
        """Submit an image-to-video task. Returns (task_id, model_used)."""
        if not image_url:
            raise ValueError("image_url is required for i2v mode")

        used_model = to_vendor_model(model, DEFAULT_I2V_MODEL)

        body: Dict[str, Any] = {
            "model": used_model,
            "images": [image_url],
            "prompt": prompt or "",
            "duration": duration,
            "resolution": resolution,
            "seed": seed,
            "movement_amplitude": movement_amplitude,
            "audio": audio,
        }

        submit_url = f"{get_provider_base_url('VIDU')}/img2video"
        logger.info(f"[Vidu] Submitting i2v task (model={used_model}, duration={duration}s)")

        resp = requests.post(submit_url, headers=self._headers(), json=body, timeout=30)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Vidu i2v submission failed (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        task_id = data.get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in Vidu response: {data}")

        return task_id, used_model

    def _submit_r2v(self, *, prompt: str, image_urls: Sequence[str], model: str = None,
                    duration: int = 5, resolution: str = "720p",
                    aspect_ratio: str = None, seed: int = 0, watermark: bool = False,
                    off_peak: bool = False, payload: str = None,
                    ) -> Tuple[str, str]:
        """Submit a reference-to-video task. Returns (task_id, model_used).

        See docs/api-reference/vidu-reference2video.md. The endpoint accepts
        either a flat `images` array or a `subjects` character library; we send
        the flat form today — subjects (named characters bound to the Cast step)
        is tracked as a follow-up.
        """
        if not image_urls:
            raise ValueError("image_urls is required for r2v mode")

        used_model = resolve_r2v_vendor_model(model)
        if used_model not in VENDOR_R2V_MODELS:
            supported = ", ".join(sorted(VENDOR_R2V_MODELS))
            raise ValueError(
                f"Vidu reference2video does not support model '{used_model}'"
                f" (requested as '{model}'). Supported r2v models: {supported}."
                " Pin the vendor api_model_id for this mode in"
                " config/model_catalog/families/vidu.yaml, or switch"
                " VIDU_PROVIDER_MODE to dashscope."
            )

        body: Dict[str, Any] = {
            "model": used_model,
            "images": list(image_urls),
            "prompt": prompt or "",
            "duration": duration,
            "resolution": resolution,
            "seed": seed,
            "watermark": watermark,
        }
        # Omit when unset so each model keeps its own default (drama -> 9:16).
        if aspect_ratio:
            body["aspect_ratio"] = aspect_ratio
        if off_peak:
            body["off_peak"] = True
        if payload:
            body["payload"] = payload

        submit_url = f"{get_provider_base_url('VIDU')}/reference2video"
        logger.info(
            f"[Vidu] Submitting r2v task (model={used_model}, duration={duration}s, "
            f"refs={len(body['images'])})"
        )

        resp = requests.post(submit_url, headers=self._headers(), json=body, timeout=30)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Vidu r2v submission failed (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        task_id = data.get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in Vidu response: {data}")

        return task_id, used_model


# ---------------------------------------------------------------------------
# Image generation (Vidu-Q series, O-protocol synchronous endpoint)
# ---------------------------------------------------------------------------

# POST /ent/v2/open/reference2image returns the finished image inline, so unlike
# every Vidu *video* endpoint there is no task id and no polling loop.
_VIDU_IMAGE_ENDPOINT = "/open/reference2image"

DEFAULT_IMAGE_MODEL = "q3-lite"

# Vidu only accepts sizes from this table - an arbitrary WxH is rejected.
# Transcribed from docs/api-reference/vidu-reference2image.md.
# (width, height, resolution_tier)
_VIDU_IMAGE_SIZES: Tuple[Tuple[int, int, str], ...] = (
    (1024, 1024, "1K"),
    (512, 2064, "1K"),
    (2046, 512, "1K"),
    (352, 2928, "1K"),
    (2928, 352, "1K"),
    (896, 1200, "1K"),
    (1200, 896, "1K"),
    (1376, 768, "1K"),
    (768, 1376, "1K"),
    (2192, 928, "1K"),
    (2048, 2048, "2K"),
    (1536, 2752, "2K"),
    (2752, 1536, "2K"),
    (4384, 1872, "4K"),
    (4800, 3584, "4K"),
    (3584, 4800, "4K"),
    (2048, 8256, "4K"),
    (8256, 2048, "4K"),
    (1408, 11712, "4K"),
    (11712, 1408, "4K"),
)

_DEFAULT_IMAGE_SIZE = "768x1376"

# Image ids in the catalog are vidu/vidu-q3-lite-image; the vendor API wants the
# bare q3-lite. Note this is a *different* naming scheme from the video models
# (viduq3-pro), so it needs its own normalizer rather than to_vendor_model().
_VENDOR_IMAGE_PREFIXES = ("vidu/", "vidu-")
_VENDOR_IMAGE_SUFFIX = "-image"


def to_vendor_image_model(model_name: Optional[str], default: str = DEFAULT_IMAGE_MODEL) -> str:
    """Normalize a catalog image model id into the bare vendor name.

    vidu/vidu-q3-lite-image -> q3-lite
    vidu-q3-fast-image      -> q3-fast
    q3-fast                 -> q3-fast   (already bare)
    q3-fast-bytoken         -> q3-fast-bytoken   (per-token billing ids pass through)
    """
    if not model_name:
        return default
    name = model_name.strip().lower()
    for prefix in _VENDOR_IMAGE_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
    if name.endswith(_VENDOR_IMAGE_SUFFIX):
        name = name[: -len(_VENDOR_IMAGE_SUFFIX)]
    return name or default


def _parse_size(size: Optional[str]) -> Optional[Tuple[int, int]]:
    """Parse '1376x768', '576*1024' or '1376 x 768' into (w, h)."""
    if not size or not isinstance(size, str):
        return None
    normalized = size.strip().lower().replace("*", "x").replace(" ", "")
    if "x" not in normalized:
        return None
    left, _, right = normalized.partition("x")
    try:
        return int(left), int(right)
    except ValueError:
        return None


def normalize_vidu_image_size(size: Optional[str]) -> str:
    """Map any requested size onto the nearest size Vidu actually accepts.

    The rest of the app speaks DashScope's '576*1024' dialect and picks
    arbitrary dimensions; Vidu only takes values from _VIDU_IMAGE_SIZES. An
    exact match passes through untouched, otherwise we keep the aspect ratio
    (the thing that actually matters for a shot) and snap to the closest
    supported size, preferring the 1K tier so we never silently upgrade the
    caller into a more expensive bracket.
    """
    parsed = _parse_size(size)
    if parsed is None:
        return _DEFAULT_IMAGE_SIZE

    width, height = parsed
    if width <= 0 or height <= 0:
        return _DEFAULT_IMAGE_SIZE

    for cand_w, cand_h, _tier in _VIDU_IMAGE_SIZES:
        if cand_w == width and cand_h == height:
            return f"{width}x{height}"

    target_ratio = width / height
    tier_rank = {"1K": 0, "2K": 1, "4K": 2}

    def _score(candidate: Tuple[int, int, str]) -> Tuple[float, int]:
        cand_w, cand_h, tier = candidate
        return (abs((cand_w / cand_h) - target_ratio), tier_rank.get(tier, 9))

    best_w, best_h, _tier = min(_VIDU_IMAGE_SIZES, key=_score)
    chosen = f"{best_w}x{best_h}"
    logger.info(
        "[Vidu] size %s is not a supported Vidu size; snapped to %s (closest aspect ratio)",
        size, chosen,
    )
    return chosen


class ViduImageModel(ImageGenModel):
    """Vidu image generation via the synchronous O-protocol endpoint.

    Vendor-only by construction: Bailian does not proxy Vidu image generation,
    so this adapter always talks to api.vidu.cn with VIDU_API_KEY and ignores
    VIDU_PROVIDER_MODE.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config or {})
        self.model_name = (self.config.get("params", {}) or {}).get(
            "model_name", DEFAULT_IMAGE_MODEL
        )

    @property
    def api_key(self) -> str:
        key = self.config.get("api_key") or os.getenv("VIDU_API_KEY", "")
        if not key:
            raise ValueError(
                "Vidu image generation requires VIDU_API_KEY. "
                "Set it in .env or in the in-app API configuration."
            )
        return key

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

    def _resolve_reference(self, ref: str, model_name: str) -> str:
        """Turn a local path / OSS key into a URL Vidu's servers can fetch."""
        resolved = resolve_media_input(
            ref,
            model_name=model_name,
            modality="image",
            backend="vendor",
            uploader=OSSImageUploader(),
        )
        return resolved.value

    def generate(
        self,
        prompt: str,
        output_path: str,
        ref_image_path: str = None,
        ref_image_paths: list = None,
        model_name: str = None,
        size: str = None,
        **kwargs,
    ) -> Tuple[str, float]:
        start_time = time.time()

        used_model = to_vendor_image_model(model_name, DEFAULT_IMAGE_MODEL)
        used_size = normalize_vidu_image_size(size)

        refs: List[str] = []
        if ref_image_path:
            refs.append(ref_image_path)
        for ref in (ref_image_paths or []):
            if ref and ref not in refs:
                refs.append(ref)

        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for ref in refs:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._resolve_reference(ref, used_model)},
                }
            )
        content.append({"type": "output_image", "image": {"size": used_size}})

        body = {
            "model": used_model,
            "messages": [{"role": "user", "content": content}],
        }

        url = f"{get_provider_base_url('VIDU')}{_VIDU_IMAGE_ENDPOINT}"
        logger.info(
            "[Vidu] Image request (model=%s, size=%s, refs=%d)",
            used_model, used_size, len(refs),
        )

        # Reference-image runs measured at ~85s against ~15s for pure text, so
        # the timeout has to clear the slow path with room to spare.
        resp = requests.post(url, headers=self._headers(), json=body, timeout=300)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Vidu image generation failed (HTTP {resp.status_code}): {resp.text}"
            )

        data = resp.json()
        entries = data.get("data") or []
        if not entries or not entries[0].get("url"):
            raise RuntimeError(f"No image URL in Vidu response: {data}")

        image_url = entries[0]["url"]
        # The URL is an S3 presign with X-Amz-Expires=86400, so it must be
        # pulled down now - it is dead within 24h and must never be stored.
        _download_vidu_image(image_url, output_path)

        generation_time = time.time() - start_time
        logger.info(
            "[Vidu] Image done in %.1fs (credits=%s) -> %s",
            generation_time, data.get("credits"), output_path,
        )
        return output_path, generation_time


def _sniff_image_format(content: bytes) -> str:
    """Identify the actual encoding of the downloaded bytes."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def _encode_image_as(content: bytes, target_format: str) -> bytes:
    """Re-encode image bytes into target_format."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "Vidu returns JPEG regardless of the requested extension, so writing "
            f"a .{target_format} file requires Pillow. Install it with "
            "`pip install pillow` (it is listed in requirements.txt)."
        ) from exc

    import io

    with Image.open(io.BytesIO(content)) as image:
        if target_format == "png":
            # JPEG has no alpha; RGB keeps the PNG lossless and avoids a
            # spurious alpha channel downstream.
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format=target_format.upper())
        return buffer.getvalue()


def _download_vidu_image(url: str, output_path: str) -> None:
    """Download a generated image and store it in the caller's requested format.

    Vidu always hands back JPEG — the documented `size` field has no format
    counterpart, and passing `format: png` is accepted but silently ignored
    (verified against the live API). Every caller in this repo builds a .png
    path and stores that path verbatim in its data model, so the bytes are
    transcoded here rather than letting a JPEG masquerade as a PNG.
    """
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
    )
    http = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    http.mount("https://", adapter)
    http.mount("http://", adapter)

    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    response = http.get(url, timeout=120)
    response.raise_for_status()
    content = response.content

    target = os.path.splitext(output_path)[1].lower().lstrip(".")
    if target == "jpg":
        target = "jpeg"
    actual = _sniff_image_format(content)

    if target and target != actual and actual != "unknown":
        logger.info("[Vidu] Transcoding %s response to %s for %s", actual, target, output_path)
        content = _encode_image_as(content, target)

    temp_path = output_path + ".tmp"
    try:
        with open(temp_path, "wb") as handle:
            handle.write(content)
        # os.replace, not os.rename: the latter raises on Windows when the
        # target already exists, which breaks regenerating into the same path.
        os.replace(temp_path, output_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


# Bare vendor names accepted by the image endpoint, per
# docs/api-reference/vidu-reference2image.md. Per-call billing ids plus their
# -bytoken counterparts.
_VIDU_IMAGE_VENDOR_NAMES = frozenset(
    base + suffix
    for base in ("q3-lite", "q3-fast", "q2-pro", "q2-fast")
    for suffix in ("", "-bytoken")
)


def is_vidu_image_model(model_name: Optional[str]) -> bool:
    """Whether a model id should be routed to Vidu's image endpoint.

    Matches the catalog ids (vidu/vidu-q3-lite-image) and the bare vendor names
    (q3-lite, q3-fast-bytoken, ...). Deliberately keyed on the -image suffix so
    it never swallows a Vidu *video* id like vidu/viduq3-pro-video.
    """
    if not model_name:
        return False
    name = model_name.strip().lower()
    if name.startswith(("vidu/", "vidu-")) and name.endswith(_VENDOR_IMAGE_SUFFIX):
        return True
    return name in _VIDU_IMAGE_VENDOR_NAMES
