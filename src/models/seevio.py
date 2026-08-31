"""Seedance video generation through Seevio (https://api.seevio.ai).

Seevio is an aggregator that resells Seedance; the keys this project holds are
`sk_live_` / `sk_test_` issued by Seevio, NOT ByteDance-direct Ark keys and NOT
MuleRouter `muk-` keys. Its wire format shares nothing with either of the other
two Seedance adapters in this package, which is why this is a separate module
rather than a flag on one of them:

    MuleRouter  POST /vendors/bytedance/v1/seedance-2.0/<mode>/generation
                flat body, `image` as base64
    Ark         POST /api/v3/contents/generations/tasks
                `content: [{type: text}, {type: image_url}]`, params as
                `--flag value` tokens inside the text
    Seevio      POST /v1/videos/generations
                `{model, input: {prompt, generation_type, image_urls[], ...}}`

The one hard constraint: Seevio documents `image_urls` / `video_urls` /
`audio_urls` as *publicly reachable* URLs and ships no upload endpoint, so
local files have to be pushed through OSS first. That is the same situation
Vidu is in, so this module reuses the shared provider-media layer rather than
inventing a second upload path — and it means Seedance now requires OSS to be
configured for anything but plain t2v.

Contract source: https://seevio.ai/zh-hant/api-docs (captured 2026-08-31, see
docs/api-reference/seedance-seevio.md). Not yet exercised against a live key,
so the base URL is env-overridable: SEEVIO_BASE_URL.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from .base import VideoGenModel
from ..utils.endpoints import get_provider_base_url
from ..utils.oss_utils import OSSImageUploader
from ..utils.provider_media import resolve_media_input

logger = logging.getLogger(__name__)

GENERATIONS_PATH = "/v1/videos/generations"
TASKS_PATH = "/v1/tasks"

# Catalog ids -> the id Seevio expects on the wire. Seevio spells versions with
# hyphens (`seedance-2-5`) where the catalog uses dots (`seedance-2.5-*`).
SEEVIO_MODEL_IDS = {
    "seedance-2.0-t2v": "seedance-2-0",
    "seedance-2.0-i2v": "seedance-2-0",
    "seedance-2.0-r2v": "seedance-2-0",
    "seedance-2.0-fast-t2v": "seedance-2-0-fast",
    "seedance-2.0-fast-i2v": "seedance-2-0-fast",
    "seedance-2.0-fast-r2v": "seedance-2-0-fast",
    "seedance-2.5-t2v": "seedance-2-5",
    "seedance-2.5-i2v": "seedance-2-5",
    "seedance-2.5-r2v": "seedance-2-5",
}

GENERATION_TYPES = {
    "t2v": "text-to-video",
    "i2v": "image-to-video",
    "r2v": "reference-to-video",
}

# Seevio asks for no more than one status poll per 10s.
POLL_INTERVAL = 10
MAX_WAIT = 1800


def resolve_seevio_model_id(model_name: Optional[str]) -> str:
    """Map a catalog id to the wire id.

    Handles the flat legacy ids (`seedance-2.0-fast-t2v`), the canonical mode
    ids (`seedance/seedance-2.5-video#r2v`), and passes anything unrecognised
    through so a newly released Seevio model can be used by pinning its id in
    project settings without a code change.
    """
    name = (model_name or "").strip()
    if not name:
        return "seedance-2-5"
    if name in SEEVIO_MODEL_IDS:
        return SEEVIO_MODEL_IDS[name]

    lowered = name.lower()
    # Canonical ids look like `seedance/seedance-2.0-fast-video#i2v`; the
    # variant is what decides the wire id, the mode does not. `-fast` is
    # checked before plain 2.0 because it is a prefix-extension of it and
    # bills differently, so it must never fall through to standard.
    if "seedance-2.5" in lowered or "seedance-2-5" in lowered:
        return "seedance-2-5"
    if "seedance-2.0-fast" in lowered or "seedance-2-0-fast" in lowered:
        return "seedance-2-0-fast"
    if "seedance-2.0" in lowered or "seedance-2-0" in lowered:
        return "seedance-2-0"
    return name


class SeevioVideoModel(VideoGenModel):
    """Seedance via Seevio's async task API: create -> poll -> download."""

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config or {})

    # -- transport -------------------------------------------------------

    def _base_url(self) -> str:
        return get_provider_base_url("SEEVIO")

    def _headers(self) -> Dict[str, str]:
        api_key = os.getenv("SEEVIO_API_KEY")
        if not api_key:
            raise RuntimeError(
                "SEEVIO_API_KEY is not configured - required for Seedance via Seevio. "
                "Get one at https://seevio.ai (key looks like sk_live_...)."
            )
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def _public_url(self, ref: str, *, model_name: Optional[str], modality: str) -> str:
        """Turn a project-side media reference into a URL Seevio can fetch.

        Remote URLs pass through untouched; local paths and object keys go to
        OSS. resolve_media_input raises with an actionable message when OSS is
        not configured, which is the only honest outcome here - Seevio cannot
        accept the bytes inline.
        """
        resolved = resolve_media_input(
            ref,
            model_name=model_name or "seedance-2.5-t2v",
            modality=modality,
            backend="seevio",
            uploader=OSSImageUploader(),
        )
        return resolved.value

    # -- body ------------------------------------------------------------

    def _build_body(
        self,
        *,
        prompt: str,
        generation_type: str,
        model_id: str,
        image_urls: Sequence[str],
        duration: Optional[int],
        resolution: Optional[str],
        aspect_ratio: Optional[str],
        seed: Optional[int],
        watermark: Optional[bool],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "generation_type": generation_type,
        }
        if image_urls:
            payload["image_urls"] = list(image_urls)
        if duration is not None:
            payload["duration"] = duration
        if resolution:
            payload["resolution"] = resolution
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio
        if watermark is not None:
            payload["watermark"] = bool(watermark)
        # `seed` is not in the documented field list, but that list is
        # demonstrably incomplete - the reference request sends `web_search`
        # and `return_last_frame`, neither of which is listed either. Sent only
        # when the user actually pinned one, so an unset seed can never be the
        # thing that trips a strict validator.
        if seed is not None:
            payload["seed"] = seed
        return {"model": model_id, "input": payload}

    # -- generation ------------------------------------------------------

    def generate(self, prompt: str, output_path: str, img_url: Optional[str] = None,
                 img_path: Optional[str] = None, **kwargs) -> Tuple[str, float]:
        start = time.time()

        model_name = kwargs.get("model_name") or kwargs.get("model")
        ref_image_urls: List[str] = list(kwargs.get("ref_image_urls") or [])
        generation_mode = (kwargs.get("generation_mode") or "").lower()

        is_r2v = generation_mode == "r2v" or bool(ref_image_urls)
        is_i2v = not is_r2v and bool(img_url or img_path)
        mode = "r2v" if is_r2v else ("i2v" if is_i2v else "t2v")

        refs: List[str] = []
        if is_i2v:
            primary = img_url or img_path
            if not primary:
                raise ValueError("Seedance I2V requires an input image")
            refs.append(primary)
        elif is_r2v:
            # The first-frame image, when present, leads the reference list:
            # Seevio maps image_urls positionally.
            primary = img_url or img_path
            if primary:
                refs.append(primary)
            for ref in ref_image_urls:
                if ref and ref not in refs:
                    refs.append(ref)
            if not refs:
                raise ValueError("Seedance R2V requires at least one reference image")

        image_urls = [
            self._public_url(ref, model_name=model_name, modality="image")
            for ref in refs
        ]

        model_id = resolve_seevio_model_id(model_name)
        body = self._build_body(
            prompt=prompt,
            generation_type=GENERATION_TYPES[mode],
            model_id=model_id,
            image_urls=image_urls,
            duration=kwargs.get("duration"),
            resolution=kwargs.get("resolution"),
            aspect_ratio=kwargs.get("aspect_ratio"),
            seed=kwargs.get("seed"),
            watermark=kwargs.get("watermark"),
        )

        url = f"{self._base_url()}{GENERATIONS_PATH}"
        logger.info("[Seevio/Seedance] POST %s model=%s mode=%s images=%d",
                    url, model_id, mode, len(image_urls))
        resp = requests.post(url, json=body, headers=self._headers(), timeout=60)
        resp.raise_for_status()
        created = resp.json() or {}
        # Documented as `taskId`; accept `task_id`/`id` too so a casing change
        # on their side does not read as "no task was created".
        task_id = created.get("taskId") or created.get("task_id") or created.get("id")
        if not task_id:
            raise RuntimeError(f"Seevio task create returned no id: {resp.text[:300]}")
        logger.info("[Seevio/Seedance] task %s created (credits=%s)",
                    task_id, created.get("credits"))

        video_url = self._poll(task_id)
        self._download(video_url, output_path)

        elapsed = time.time() - start
        logger.info("[Seevio/Seedance] done in %.1fs -> %s", elapsed, output_path)
        return output_path, elapsed

    def _poll(self, task_id: str) -> str:
        url = f"{self._base_url()}{TASKS_PATH}/{task_id}"
        deadline = time.time() + MAX_WAIT
        while time.time() < deadline:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json() or {}
            status = (data.get("status") or "").lower()
            if status == "completed":
                results = (data.get("data") or {}).get("results") or []
                video_url = next((item for item in results if item), None)
                if not video_url:
                    raise RuntimeError(
                        f"Seevio task {task_id} completed without a video url: {data}"
                    )
                return video_url
            if status == "failed":
                raise RuntimeError(
                    f"Seevio generation failed: {data.get('failed_reason') or data}"
                )
            time.sleep(POLL_INTERVAL)
        raise TimeoutError(f"Seevio task {task_id} did not finish within {MAX_WAIT}s")

    def _download(self, url: str, output_path: str) -> None:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with requests.get(url, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    fh.write(chunk)
