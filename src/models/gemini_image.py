"""Google Gemini image generation (text-to-image and image-to-image).

Replaces the DashScope-backed Wanx adapter. Uses the native `generateContent`
endpoint with `responseModalities: ["IMAGE"]`, which returns the image inline
as base64 under `candidates[].content.parts[].inlineData`.

Endpoint choice is based on probing the live API on 2026-09-08: the newer
`/v1beta/interactions` endpoint also works, but buries the image at
`steps[1].content[0].data`, while `generateContent` returns it one level deep
and accepts `imageConfig.aspectRatio` directly. Both were verified to honour
the requested aspect ratio (a 9:16 request came back 768x1376).

Gemini has no separate negative-prompt field, so negatives are folded into the
prompt text. It accepts up to 14 reference images per request (10 objects +
4 character-consistency + 3 style, per the model docs); more than that fails
the whole request, so we truncate.
"""
import base64
import logging
import mimetypes
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from ..utils.endpoints import get_provider_base_url
from .image import ImageGenModel

logger = logging.getLogger(__name__)

DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image"

# Aspect ratios the API accepts, as (label, width/height).
_SUPPORTED_RATIOS: List[Tuple[str, float]] = [
    ("1:1", 1 / 1),
    ("3:2", 3 / 2),
    ("2:3", 2 / 3),
    ("3:4", 3 / 4),
    ("4:3", 4 / 3),
    ("4:5", 4 / 5),
    ("5:4", 5 / 4),
    ("9:16", 9 / 16),
    ("16:9", 16 / 9),
    ("21:9", 21 / 9),
]

# Per the model docs: 10 objects + 4 character-consistency + 3 style, but the
# hard per-request ceiling is 14. Going over fails the request outright.
MAX_REFERENCE_IMAGES = 14

_REQUEST_TIMEOUT = 300


def size_to_aspect_ratio(size: Optional[str]) -> str:
    """Map the project's ``"WIDTH*HEIGHT"`` size string to a Gemini aspect ratio.

    Falls back to ``"1:1"`` when the value is missing or unparseable: an
    unexpected square beats breaking the whole storyboard run, and the caller
    has no better answer to offer either.
    """
    text = (size or "").strip()
    if "*" not in text:
        return "1:1"
    raw_w, _, raw_h = text.partition("*")
    try:
        width, height = float(raw_w), float(raw_h)
    except ValueError:
        return "1:1"
    if width <= 0 or height <= 0:
        return "1:1"

    target = width / height
    return min(_SUPPORTED_RATIOS, key=lambda item: abs(item[1] - target))[0]


class GeminiImageModel(ImageGenModel):
    """Image generation via Gemini's native generateContent endpoint."""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config or {})
        self.params = self.config.get("params", {}) or {}

    @property
    def api_key(self) -> str:
        key = self.config.get("api_key") or os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise ValueError(
                "Gemini image generation requires GEMINI_API_KEY. "
                "Set it in .env or in the in-app API configuration."
            )
        return key

    def _endpoint(self, model_name: str) -> str:
        base = get_provider_base_url("GEMINI")
        return f"{base}/v1beta/models/{model_name}:generateContent"

    @staticmethod
    def _collect_references(
        ref_image_path: Optional[str], ref_image_paths: Optional[List[str]]
    ) -> List[str]:
        """Merge the single-path and list forms, de-duplicated, order preserved."""
        merged: List[str] = []
        for ref in [ref_image_path, *(ref_image_paths or [])]:
            if ref and ref not in merged:
                merged.append(ref)
        return merged

    @staticmethod
    def _inline_part(path: str) -> Optional[Dict[str, Any]]:
        """Read a local image into an inline_data part, or None if unreadable.

        A missing reference should cost us that one reference, not the whole
        generation — asset files get moved and cleaned up behind our back.
        """
        try:
            raw = open(path, "rb").read()
        except OSError as e:
            logger.warning("Skipping unreadable reference image %s: %s", path, e)
            return None
        mime = mimetypes.guess_type(path)[0] or "image/png"
        return {
            "inline_data": {
                "mime_type": mime,
                "data": base64.b64encode(raw).decode("ascii"),
            }
        }

    def _build_parts(
        self, prompt: str, references: List[str], negative_prompt: Optional[str]
    ) -> List[Dict[str, Any]]:
        parts: List[Dict[str, Any]] = []

        if len(references) > MAX_REFERENCE_IMAGES:
            logger.warning(
                "Gemini accepts at most %d reference images; dropping %d of %d.",
                MAX_REFERENCE_IMAGES, len(references) - MAX_REFERENCE_IMAGES, len(references),
            )
            references = references[:MAX_REFERENCE_IMAGES]

        for ref in references:
            part = self._inline_part(ref)
            if part:
                parts.append(part)

        text = prompt or ""
        if negative_prompt and negative_prompt.strip():
            # No dedicated field exists; dropping it silently would make
            # constraints like "no watermark" quietly stop working.
            text = f"{text}\n\n避免出现：{negative_prompt.strip()}"
        parts.append({"text": text})
        return parts

    @staticmethod
    def _extract_image(payload: Dict[str, Any]) -> bytes:
        """Pull the image bytes out of the response, or explain why there are none.

        `parts` routinely contains a leading text part, so scan rather than
        index. A text-only response means the model refused (safety filter,
        unsupported request) — surface its wording instead of writing an
        empty file that only fails later during video assembly.
        """
        candidates = payload.get("candidates") or []
        texts: List[str] = []
        for candidate in candidates:
            for part in (candidate.get("content", {}) or {}).get("parts", []) or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"])
                if part.get("text"):
                    texts.append(part["text"])
        detail = " ".join(texts).strip()
        raise RuntimeError(
            f"Gemini returned no image. Model said: {detail}" if detail
            else "Gemini returned no image and gave no reason."
        )

    def generate(
        self,
        prompt: str,
        output_path: str,
        ref_image_path: str = None,
        ref_image_paths: list = None,
        model_name: str = None,
        size: str = None,
        negative_prompt: str = None,
        **kwargs,
    ) -> Tuple[str, float]:
        start = time.time()
        used_model = model_name or self.params.get("model_name") or DEFAULT_IMAGE_MODEL
        aspect_ratio = size_to_aspect_ratio(size)
        references = self._collect_references(ref_image_path, ref_image_paths)

        payload = {
            "contents": [{"parts": self._build_parts(prompt, references, negative_prompt)}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": aspect_ratio},
            },
        }

        logger.info(
            "Gemini image: model=%s aspect=%s refs=%d",
            used_model, aspect_ratio, len(references),
        )

        response = requests.post(
            self._endpoint(used_model),
            # Header rather than a query param so the key never lands in
            # access logs or an exception's request URL.
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        )
        if not response.ok:
            raise RuntimeError(
                f"Gemini image API error {response.status_code}: {response.text[:500]}"
            )

        image_bytes = self._extract_image(response.json())

        directory = os.path.dirname(output_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(output_path, "wb") as fh:
            fh.write(image_bytes)

        return output_path, time.time() - start
