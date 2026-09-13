"""Playground service layer -- orchestrates AI generation by delegating to existing model adapters.

Routes based on model_id to the appropriate adapter (BytePlusVideoModel, KlingModel,
ViduModel, GeminiImageModel).  Mirrors the
routing logic in ``src/apps/comic_gen/pipeline.py:process_video_task()``.
"""

import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Optional

from .models import (
    GenerateRequest,
    PlaygroundGeneration,
    PlaygroundMode,
    PlaygroundOutput,
)
from .storage import PlaygroundStorage
from ...utils import get_logger
from ...utils.system_check import get_ffmpeg_path

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Output directories
# ---------------------------------------------------------------------------
IMAGE_OUTPUT_DIR = os.path.join("output", "playground", "images")
VIDEO_OUTPUT_DIR = os.path.join("output", "playground", "videos")
VIDEO_THUMBNAIL_DIR = os.path.join("output", "playground", "thumbnails")


class PlaygroundService:
    """High-level service that creates generation records and delegates to
    the correct model adapter for execution."""

    def __init__(self, storage: PlaygroundStorage):
        self.storage = storage
        # Lazy-initialised model instances (cached for the lifetime of the service)
        self._default_video_model = None
        self._default_image_model = None
        self._kling_model = None
        self._vidu_model = None
        self._byteplus_video_model = None
        self._vidu_image_model = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_generation(self, request: GenerateRequest, owner_id: str = "") -> PlaygroundGeneration:
        """Create a :class:`PlaygroundGeneration` record with *status=pending*,
        persist it via storage, and return it."""
        gen = PlaygroundGeneration(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            mode=request.mode,
            model_id=request.model_id,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            input_media=request.input_media or [],
            parameters=request.parameters or {},
            batch_size=request.batch_size or 1,
            outputs=[],
            status="pending",
            error=None,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.storage.add_generation(gen)
        return gen

    def estimate_cost(
        self, mode: PlaygroundMode, model_id: str, parameters: Optional[dict], batch_size: int = 1
    ) -> "tuple[Optional[float], Optional[float], bool]":
        """Pre-generation cost estimate: (total_cost, per_unit_cost, priced).

        Only Seedance (BytePlus) has a confirmed price table; every other
        provider returns (None, None, False) -- count-only, no cost known
        until pricing is confirmed (see usage-tracking design doc scope)."""
        model_lower = (model_id or "").lower()
        if not model_lower.startswith("seedance"):
            return None, None, False

        from ..comic_gen import usage_repo
        from ...models.byteplus import resolve_ark_model_id

        wire_model_id = resolve_ark_model_id(model_id)
        if wire_model_id is None:
            return None, None, False

        params = parameters or {}
        resolution = params.get("resolution", "720p")
        duration = params.get("duration", 5)
        per_unit = usage_repo.estimate_seedance_cost_usd(
            model=wire_model_id,
            resolution=resolution,
            duration=duration,
            input_has_video=(mode == PlaygroundMode.R2V),
        )
        if per_unit is None:
            return None, None, False
        return per_unit * max(batch_size, 1), per_unit, True

    def process_generation(self, generation_id: str) -> None:
        """Execute the actual generation.  Intended to run in a background
        thread -- all calls are synchronous (blocking)."""
        gen = self.storage.get_generation(generation_id)
        if gen is None:
            logger.error("Generation %s not found", generation_id)
            return

        # Mark processing
        gen.status = "processing"
        self.storage.update_generation(gen)

        try:
            mode = gen.mode
            if mode in (PlaygroundMode.T2I, PlaygroundMode.I2I):
                self._process_image_generation(gen)
            elif mode in (PlaygroundMode.T2V, PlaygroundMode.I2V, PlaygroundMode.R2V, PlaygroundMode.V2V):
                self._process_video_generation(gen)
            else:
                raise ValueError(f"Unsupported playground mode: {mode}")

            gen.status = "completed"
        except Exception as exc:
            logger.exception("Generation %s failed", generation_id)
            gen.status = "failed"
            gen.error = str(exc)

        self.storage.update_generation(gen)

    def save_to_library(self, generation_id: str, output_id: str, category: str = "general") -> bool:
        """Copy a generated output to ``output/assets/{category}/`` and flag
        :pyattr:`PlaygroundOutput.saved_to_library` = True."""
        gen = self.storage.get_generation(generation_id)
        if gen is None:
            logger.warning("save_to_library: generation %s not found", generation_id)
            return False

        target_output: Optional[PlaygroundOutput] = None
        for out in gen.outputs:
            if out.id == output_id:
                target_output = out
                break
        if target_output is None:
            logger.warning("save_to_library: output %s not found in generation %s", output_id, generation_id)
            return False

        # media_path is stored as e.g. "output/playground/images/t2i_xxx_0.png"
        # Normalise: try as-is first, then strip leading "output/" and re-join
        src_path = target_output.media_path
        if not os.path.isfile(src_path):
            alt = os.path.join("output", target_output.media_path)
            if os.path.isfile(alt):
                src_path = alt
        if not os.path.isfile(src_path):
            logger.error("save_to_library: source file not found: %s", target_output.media_path)
            return False

        dest_dir = os.path.join("output", "assets", category)
        os.makedirs(dest_dir, exist_ok=True)

        dest_path = os.path.join(dest_dir, os.path.basename(src_path))
        shutil.copy2(src_path, dest_path)
        logger.info("Saved output %s to library: %s", output_id, dest_path)

        # Wave A (shared asset pool): besides copying the file, register a real
        # global library asset record so the output is curatable through the
        # /library/assets CRUD. category -> asset_type mapping; anything
        # unknown (incl. the "general" default) falls back to "prop".
        asset_type = self._category_to_asset_type(category)
        prompt_text = (gen.prompt or "").strip()
        asset_name = prompt_text[:40] or os.path.splitext(os.path.basename(dest_path))[0]
        try:
            # Deferred import: comic_gen.api owns the live ComicGenPipeline
            # singleton -- the same instance that backs the /library/assets
            # CRUD endpoints, so the new asset is immediately visible there.
            # A top-level import would create a cycle (comic_gen.api imports the
            # playground router at module load), so we import lazily at call
            # time when both modules are fully initialised.
            from ..comic_gen.api import pipeline as comic_pipeline

            asset = comic_pipeline.create_library_asset(
                asset_type,
                {
                    "name": asset_name,
                    "description": prompt_text,
                    # Point the library record at the freshly-copied file.
                    "image_url": dest_path,
                },
            )
            logger.info(
                "save_to_library: created global %s asset %s from output %s",
                asset_type,
                getattr(asset, "id", "?"),
                output_id,
            )
        except Exception:
            logger.exception(
                "save_to_library: failed to register global library asset for output %s",
                output_id,
            )
            return False

        target_output.saved_to_library = True
        self.storage.update_generation(gen)
        return True

    # ------------------------------------------------------------------
    # Image generation (t2i / i2i)
    # ------------------------------------------------------------------

    def _process_image_generation(self, gen: PlaygroundGeneration) -> None:
        # Imported here, like every other adapter in this module, so importing
        # the service does not drag in the heavy model dependencies.
        from ...models.vidu import is_vidu_image_model

        os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)

        model_lower = gen.model_id.lower()
        failures = []

        for idx in range(gen.batch_size):
            ext = "png"
            out_filename = f"{gen.mode.value}_{gen.id}_{idx}.{ext}"
            out_path = os.path.join(IMAGE_OUTPUT_DIR, out_filename)

            try:
                if is_vidu_image_model(model_lower):
                    self._generate_image_vidu(gen, out_path, idx)
                else:
                    self._generate_image_default(gen, out_path, idx)

                output_entry = PlaygroundOutput(
                    id=str(uuid.uuid4()),
                    media_path=out_path,
                    media_type="image",
                )
                gen.outputs.append(output_entry)
                self.storage.update_generation(gen)
            except Exception as exc:
                logger.error("Image generation %s batch %d failed: %s", gen.id, idx, exc)
                failures.append(str(exc))

        if failures and not gen.outputs:
            raise RuntimeError(f"All {len(failures)} batch items failed: {failures[0]}")

    def _generate_image_default(self, gen: PlaygroundGeneration, out_path: str, _idx: int) -> None:
        """Delegate to :class:`GeminiImageModel` (default image generation)."""
        from ...models.gemini_image import GeminiImageModel

        if self._default_image_model is None:
            self._default_image_model = GeminiImageModel({})

        params = gen.parameters
        kwargs = {
            "model_name": gen.model_id,
            "size": params.get("size", "1280*1280"),
            "n": 1,
            "negative_prompt": gen.negative_prompt,
            "seed": params.get("seed"),
            "prompt_extend": params.get("prompt_extend", True),
            "watermark": params.get("watermark", False),
        }

        # i2i: attach reference images from input_media
        ref_paths = list(gen.input_media) if gen.mode == PlaygroundMode.I2I else []
        if ref_paths:
            kwargs["ref_image_paths"] = ref_paths

        self._default_image_model.generate(
            prompt=gen.prompt,
            output_path=out_path,
            **kwargs,
        )

    def _generate_image_vidu(self, gen: PlaygroundGeneration, out_path: str, _idx: int) -> None:
        """Delegate to :class:`ViduImageModel` (Vidu-Q sync image endpoint)."""
        from ...models.vidu import ViduImageModel

        if self._vidu_image_model is None:
            self._vidu_image_model = ViduImageModel({})

        params = gen.parameters
        kwargs = {
            "model_name": gen.model_id,
            "size": params.get("size"),
        }

        # i2i: attach reference images
        if gen.mode == PlaygroundMode.I2I and gen.input_media:
            kwargs["ref_image_paths"] = list(gen.input_media)

        self._vidu_image_model.generate(
            prompt=gen.prompt,
            output_path=out_path,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Video generation (t2v / i2v / r2v / v2v)
    # ------------------------------------------------------------------

    def _process_video_generation(self, gen: PlaygroundGeneration) -> None:
        os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

        model_lower = gen.model_id.lower()
        failures = []

        for idx in range(gen.batch_size):
            out_filename = f"{gen.mode.value}_{gen.id}_{idx}.mp4"
            out_path = os.path.join(VIDEO_OUTPUT_DIR, out_filename)

            try:
                if model_lower.startswith("seedance"):
                    usage = self._generate_video_seedance(gen, out_path)
                elif model_lower.startswith("kling"):
                    usage = self._generate_video_kling(gen, out_path)
                elif model_lower.startswith("vidu") or model_lower.startswith("viduq"):
                    usage = self._generate_video_vidu(gen, out_path)
                else:
                    # happyhorse / pixverse 随 DashScope 下线，专属分支已移除；
                    # 未识别的 id 一并落到 Seedance 兜底。
                    usage = self._generate_video_default(gen, out_path)

                total_tokens, cost_usd = self._record_video_usage(gen, usage)
                output_entry = PlaygroundOutput(
                    id=str(uuid.uuid4()),
                    media_path=out_path,
                    media_type="video",
                    thumbnail_path=self._extract_video_thumbnail(out_path),
                    total_tokens=total_tokens,
                    cost_usd=cost_usd,
                )
                gen.outputs.append(output_entry)
                self.storage.update_generation(gen)
            except Exception as exc:
                logger.error("Video generation %s batch %d failed: %s", gen.id, idx, exc)
                failures.append(str(exc))

        if failures and not gen.outputs:
            raise RuntimeError(f"All {len(failures)} batch items failed: {failures[0]}")

    def _record_video_usage(
        self, gen: PlaygroundGeneration, usage: Optional[dict]
    ) -> "tuple[Optional[int], Optional[float]]":
        """Best-effort usage_events write; never fails the generation itself.

        Returns (total_tokens, cost_usd) so the caller can surface the same
        numbers on the PlaygroundOutput record, regardless of whether the
        usage_events write itself succeeds.
        """
        if usage is None:
            return None, None

        from ..comic_gen import usage_repo

        total_tokens = usage.get("total_tokens")
        cost_usd = None
        try:
            cost_usd = usage_repo.record_generation_usage(
                user_id=gen.owner_id or "",
                kind="video",
                provider=usage.get("provider", "unknown"),
                model=self._resolve_wire_model_id(gen.model_id) or gen.model_id,
                resolution=usage.get("resolution"),
                input_has_video=usage.get("input_has_video"),
                duration=usage.get("duration"),
                total_tokens=total_tokens,
            )
        except Exception:
            logger.warning("Failed to record generation usage for %s", gen.id, exc_info=True)

        return total_tokens, cost_usd

    @staticmethod
    def _resolve_wire_model_id(model_id: str) -> Optional[str]:
        from ...models.byteplus import resolve_ark_model_id

        return resolve_ark_model_id(model_id)

    def _extract_video_thumbnail(self, video_path: str) -> Optional[str]:
        """Grab a frame just past the start of the clip as a gallery thumbnail.

        Best-effort: a thumbnail failure must not fail the generation itself,
        since the video is already saved by the time this runs.
        """
        ffmpeg_path = get_ffmpeg_path()
        if not ffmpeg_path:
            logger.warning("FFmpeg not found; skipping thumbnail for %s", video_path)
            return None

        os.makedirs(VIDEO_THUMBNAIL_DIR, exist_ok=True)
        thumb_filename = f"{os.path.splitext(os.path.basename(video_path))[0]}.jpg"
        thumb_path = os.path.join(VIDEO_THUMBNAIL_DIR, thumb_filename)

        cmd = [
            ffmpeg_path, "-ss", "0.1",
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "3",
            "-y", thumb_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0 or not os.path.exists(thumb_path):
                logger.warning(
                    "Thumbnail extraction failed for %s: %s", video_path, result.stderr[:300]
                )
                return None
        except subprocess.TimeoutExpired:
            logger.warning("Thumbnail extraction timed out for %s", video_path)
            return None

        return thumb_path

    # -- adapter delegates ------------------------------------------------

    def _generate_video_default(self, gen: PlaygroundGeneration, out_path: str) -> Optional[dict]:
        """Delegate to :class:`BytePlusVideoModel` (Seedance on BytePlus Ark)."""
        from ...models.byteplus import BytePlusVideoModel

        if self._default_video_model is None:
            self._default_video_model = BytePlusVideoModel({})

        params = gen.parameters
        img_path, img_url = self._resolve_first_input_media(gen)

        kwargs = {
            "model": gen.model_id,
            "duration": params.get("duration", 5),
            "resolution": params.get("resolution", "720P"),
            "seed": params.get("seed"),
            "negative_prompt": gen.negative_prompt,
            "prompt_extend": params.get("prompt_extend", True),
            "watermark": params.get("watermark", False),
            "ratio": params.get("ratio"),
            "audio_url": params.get("audio_url"),
        }

        # r2v: reference images
        if gen.mode == PlaygroundMode.R2V and gen.input_media:
            kwargs["ref_image_urls"] = list(gen.input_media)

        # v2v: video input
        if gen.mode == PlaygroundMode.V2V and gen.input_media:
            kwargs["video_url"] = gen.input_media[0]

        self._default_video_model.generate(
            prompt=gen.prompt,
            output_path=out_path,
            img_path=img_path,
            img_url=img_url,
            **kwargs,
        )
        return None  # count-only -- no confirmed price table for wanx yet

    def _generate_video_seedance(self, gen: PlaygroundGeneration, out_path: str) -> Optional[dict]:
        """Seedance runs entirely on BytePlus Ark.

        The family used to straddle two gateways; MuleRouter is gone, so there
        is a single path now.
        """
        params = gen.parameters
        img_path, img_url = self._resolve_first_input_media(gen)

        kwargs = {
            "duration": params.get("duration", 5),
            "resolution": params.get("resolution", "720p"),
            "aspect_ratio": params.get("aspect_ratio", "adaptive"),
            "seed": params.get("seed"),
            "watermark": params.get("watermark", False),
            # The adapter derives the wire model id (2.0 vs fast vs mini vs
            # 2.5) from this. Playground never sent it, so every fast-variant
            # run here silently billed and rendered as the standard variant.
            "model_name": gen.model_id,
        }

        # r2v: reference images
        if gen.mode == PlaygroundMode.R2V and gen.input_media:
            kwargs["generation_mode"] = "r2v"
            kwargs["ref_image_urls"] = list(gen.input_media)

        # v2v: the source clip, plus the optional edit / extend sub-type.
        # Without this the source video never reaches the adapter and the
        # request goes out as a plain prompt-only generation — it succeeds,
        # bills, and returns something unrelated to the clip the user picked.
        if gen.mode == PlaygroundMode.V2V and gen.input_media:
            kwargs["video_url"] = gen.input_media[0]
            task_type = params.get("task_type")
            if task_type:
                kwargs["task_type"] = task_type

        # i2v: optional second entry is the last frame (Ark first_frame +
        # last_frame scenario). Only img_url is wired through to Ark today
        # (see note on img_path below), so a local-file last frame is
        # unsupported the same way a local-file first frame already is.
        if gen.mode == PlaygroundMode.I2V and len(gen.input_media) > 1:
            _, last_frame_url = self._resolve_input_media_at(gen, 1)
            if last_frame_url:
                kwargs["last_frame_url"] = last_frame_url

        from ...models.byteplus import BytePlusVideoModel

        if self._byteplus_video_model is None:
            self._byteplus_video_model = BytePlusVideoModel({})
        model = self._byteplus_video_model

        _, _, usage = model.generate(
            prompt=gen.prompt,
            output_path=out_path,
            img_url=img_url,
            img_path=img_path,
            **kwargs,
        )
        return {
            "provider": "byteplus",
            "resolution": kwargs["resolution"],
            "input_has_video": gen.mode == PlaygroundMode.R2V,
            "duration": kwargs["duration"],
            "total_tokens": (usage or {}).get("total_tokens"),
        }

    def _generate_video_kling(self, gen: PlaygroundGeneration, out_path: str) -> Optional[dict]:
        """Delegate to :class:`KlingModel`."""
        from ...models.kling import KlingModel

        if self._kling_model is None:
            self._kling_model = KlingModel({})

        params = gen.parameters
        img_path, img_url = self._resolve_first_input_media(gen)

        self._kling_model.generate(
            prompt=gen.prompt,
            output_path=out_path,
            img_url=img_url,
            img_path=img_path,
            duration=params.get("duration", 5),
            model=gen.model_id,
            negative_prompt=gen.negative_prompt,
            aspect_ratio=params.get("aspect_ratio", "16:9"),
            mode=params.get("mode", "std"),
            sound=params.get("sound", "off"),
            cfg_scale=params.get("cfg_scale"),
        )
        return None  # count-only -- no confirmed price table for kling yet

    def _generate_video_vidu(self, gen: PlaygroundGeneration, out_path: str) -> Optional[dict]:
        """Delegate to :class:`ViduModel`."""
        from ...models.vidu import ViduModel

        if self._vidu_model is None:
            self._vidu_model = ViduModel({})

        params = gen.parameters
        img_path, img_url = self._resolve_first_input_media(gen)

        self._vidu_model.generate(
            prompt=gen.prompt,
            output_path=out_path,
            img_url=img_url,
            img_path=img_path,
            duration=params.get("duration", 5),
            model=gen.model_id,
            resolution=params.get("resolution", "720p"),
            aspect_ratio=params.get("aspect_ratio", "16:9"),
            seed=params.get("seed", 0),
            audio=params.get("audio", True),
            movement_amplitude=params.get("movement_amplitude", "auto"),
        )
        return None  # count-only -- no confirmed price table for vidu yet

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _category_to_asset_type(category: Optional[str]) -> str:
        """Map a Playground save category to a global-library asset_type.

        Known categories (``character`` / ``scene`` / ``prop``) pass through;
        everything else -- including the ``"general"`` default, empty string,
        or ``None`` -- falls back to ``"prop"``."""
        normalized = (category or "").strip().lower()
        if normalized in ("character", "scene", "prop"):
            return normalized
        return "prop"

    @classmethod
    def _resolve_first_input_media(cls, gen: PlaygroundGeneration):
        """Return ``(img_path, img_url)`` for the first entry in
        :pyattr:`input_media`.  Local files are returned as *img_path*;
        remote URLs as *img_url*."""
        return cls._resolve_input_media_at(gen, 0)

    @staticmethod
    def _resolve_input_media_at(gen: PlaygroundGeneration, index: int):
        """Return ``(path, url)`` for ``input_media[index]``. Local files are
        returned as *path*; remote URLs (or anything unresolvable locally) as
        *url*. ``(None, None)`` when there is no entry at that index."""
        if index >= len(gen.input_media):
            return None, None

        entry = gen.input_media[index]
        if entry.startswith(("http://", "https://")):
            return None, entry

        # Try as-is, then relative to output/
        if os.path.exists(entry):
            return entry, None
        candidate = os.path.join("output", entry)
        if os.path.exists(candidate):
            return candidate, None

        # Fall back to treating it as a URL-like reference
        return None, entry
