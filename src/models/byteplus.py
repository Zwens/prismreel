"""BytePlus ModelArk / Volcano Ark video generation (the Seedance family:
2.0, 2.0 fast, 2.0 mini, 2.5).

Why REST rather than the `volcenginesdkarkruntime` SDK the older DoubaoModel
uses: the SDK is not installed in this environment, and pulling in a vendor SDK
for three HTTP calls buys nothing that `requests` (already a dependency) does
not. The wire format is taken from that SDK's own usage in models/doubao.py —
`tasks.create(model=..., content=[{type: text}, {type: image_url}])` plus
`tasks.get(task_id)` — which is the Ark v3 contract this module speaks directly.

Verified live 2026-08-30: both hosts below answer `401 AuthenticationError`,
confirming host + `/api/v3` prefix are real. Auth is checked BEFORE parameter
validation on Ark (the opposite of MuleRouter), so the request body could NOT
be probed without a key. Host and path are env-overridable; the wire model id
is not — it is looked up from ARK_MODEL_IDS below, and an unrecognised catalog
id makes generate() raise rather than guessing.

    ARK_API_KEY    credential (required)
    ARK_REGION     "intl" (default) | "cn"
    ARK_BASE_URL   full override, wins over ARK_REGION
    ARK_TASKS_PATH override for the task path
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from .base import VideoGenModel

logger = logging.getLogger(__name__)

ARK_HOSTS = {
    "intl": "https://ark.ap-southeast.bytepluses.com/api/v3",
    "cn": "https://ark.cn-beijing.volces.com/api/v3",
}

DEFAULT_TASKS_PATH = "/contents/generations/tasks"

# Catalog ids -> the id Ark expects on the wire. Both the flat legacy id
# (seedance-2.0-fast-t2v) and the catalog canonical id
# (seedance/seedance-2.0-fast-video#t2v) have to resolve, because playground
# holds the former and the comic pipeline holds the latter.
ARK_MODEL_IDS = {
    "seedance-2.0-t2v": "dreamina-seedance-2-0-260128",
    "seedance-2.0-i2v": "dreamina-seedance-2-0-260128",
    "seedance-2.0-r2v": "dreamina-seedance-2-0-260128",
    "seedance-2.0-fast-t2v": "dreamina-seedance-2-0-fast-260128",
    "seedance-2.0-fast-i2v": "dreamina-seedance-2-0-fast-260128",
    "seedance-2.0-fast-r2v": "dreamina-seedance-2-0-fast-260128",
    "seedance-2.0-mini-t2v": "dreamina-seedance-2-0-mini-260615",
    "seedance-2.0-mini-i2v": "dreamina-seedance-2-0-mini-260615",
    "seedance-2.0-mini-r2v": "dreamina-seedance-2-0-mini-260615",
    "seedance-2.5-t2v": "dreamina-seedance-2-5-260628",
    "seedance-2.5-i2v": "dreamina-seedance-2-5-260628",
    "seedance-2.5-r2v": "dreamina-seedance-2-5-260628",
}

POLL_INTERVAL = 5
MAX_WAIT = 1800


def resolve_ark_model_id(model_name: Optional[str]) -> Optional[str]:
    """Map a catalog id to the wire model id Ark expects.

    Pure by design: the model instance is cached and shared across tasks, so
    resolving into instance state would let one shot's variant leak into the
    next. Returns None for anything unrecognised rather than defaulting to the
    standard variant — fast and mini bill differently, so a silent fallback
    would misbill instead of failing loudly.
    """
    if not model_name:
        return None

    flat = model_name.strip().lower()
    if flat in ARK_MODEL_IDS:
        return ARK_MODEL_IDS[flat]

    # Canonical form: seedance/seedance-2.0-fast-video#t2v
    if "#" in flat:
        family_part, _, mode = flat.partition("#")
        base = family_part.rsplit("/", 1)[-1]
        if base.endswith("-video"):
            base = base[: -len("-video")]
        candidate = f"{base}-{mode}"
        if candidate in ARK_MODEL_IDS:
            return ARK_MODEL_IDS[candidate]

    return None


def resolve_ark_base_url() -> str:
    """Ark base URL: explicit override, else region, else international."""
    override = (os.getenv("ARK_BASE_URL") or "").strip()
    if override:
        return override.rstrip("/")
    region = (os.getenv("ARK_REGION") or "intl").strip().lower()
    return ARK_HOSTS.get(region, ARK_HOSTS["intl"])


def build_param_flags(
    *,
    resolution: Optional[str],
    duration: Optional[int],
    ratio: Optional[str],
    watermark: Optional[bool],
) -> str:
    """Ark takes generation parameters as `--flag value` tokens inside the text
    item, not as JSON fields. Unset values are omitted so the model applies its
    own default rather than receiving a literal "None"."""
    parts: List[str] = []
    if resolution:
        parts.append(f"--resolution {resolution}")
    if duration is not None:
        parts.append(f"--duration {duration}")
    if ratio:
        parts.append(f"--ratio {ratio}")
    if watermark is not None:
        # Lowercase: these are text tokens, Python's "True" would not match.
        parts.append(f"--watermark {'true' if watermark else 'false'}")
    return " ".join(parts)


def build_ark_content(prompt: str, images: List[str], flags: str) -> List[Dict[str, Any]]:
    """The `content` array: one text item, then one image_url item per
    reference. Order is preserved — for R2V it is what the model maps to its
    reference slots."""
    text = " ".join(part for part in [(prompt or "").strip(), flags.strip()] if part)
    content: List[Dict[str, Any]] = [{"type": "text", "text": text}]
    for url in images:
        if url:
            content.append({"type": "image_url", "image_url": {"url": url}})
    return content


class BytePlusVideoModel(VideoGenModel):
    """The Seedance family (2.0, 2.0 fast, 2.0 mini, 2.5) via Ark's async task
    API: create -> poll -> download."""

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config or {})

    # -- helpers ---------------------------------------------------------

    def resolve_model_id(self, model_name: Optional[str]) -> Optional[str]:
        return resolve_ark_model_id(model_name)

    def _headers(self) -> Dict[str, str]:
        api_key = os.getenv("ARK_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ARK_API_KEY is not configured — required for BytePlus ModelArk."
            )
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def _tasks_url(self) -> str:
        path = (os.getenv("ARK_TASKS_PATH") or DEFAULT_TASKS_PATH).strip()
        return f"{resolve_ark_base_url()}{path}"

    # -- generation ------------------------------------------------------

    def generate(self, prompt: str, output_path: str, img_url: Optional[str] = None,
                 img_path: Optional[str] = None, **kwargs) -> Tuple[str, float]:
        start = time.time()

        images: List[str] = []
        if img_url:
            images.append(img_url)
        for ref in kwargs.get("ref_image_urls") or []:
            if ref and ref not in images:
                images.append(ref)

        model_name = kwargs.get("model_name")
        wire_model_id = self.resolve_model_id(model_name)
        if wire_model_id is None:
            # Fail before the network call: a None model id would otherwise
            # be POSTed straight to Ark, which wastes a round trip on an
            # opaque vendor-side 400 with no hint of which id was bad.
            raise ValueError(f"Unrecognized Seedance model id: {model_name!r}")

        flags = build_param_flags(
            resolution=kwargs.get("resolution"),
            duration=kwargs.get("duration"),
            ratio=kwargs.get("aspect_ratio"),
            watermark=kwargs.get("watermark"),
        )
        body = {
            "model": wire_model_id,
            "content": build_ark_content(prompt, images, flags),
        }

        url = self._tasks_url()
        logger.info("[BytePlus/Seedance] POST %s model=%s images=%d",
                    url, body["model"], len(images))
        resp = requests.post(url, json=body, headers=self._headers(), timeout=60)
        resp.raise_for_status()
        task_id = (resp.json() or {}).get("id")
        if not task_id:
            raise RuntimeError(f"Ark task create returned no id: {resp.text[:300]}")

        video_url = self._poll(task_id)
        self._download(video_url, output_path)

        elapsed = time.time() - start
        logger.info("[BytePlus/Seedance] done in %.1fs -> %s", elapsed, output_path)
        return output_path, elapsed

    def _poll(self, task_id: str) -> str:
        url = f"{self._tasks_url()}/{task_id}"
        deadline = time.time() + MAX_WAIT
        while time.time() < deadline:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json() or {}
            status = data.get("status")
            if status == "succeeded":
                video_url = ((data.get("content") or {}).get("video_url"))
                if not video_url:
                    raise RuntimeError(f"Ark task succeeded without a video url: {data}")
                return video_url
            if status == "failed":
                raise RuntimeError(f"Ark generation failed: {data.get('error')}")
            time.sleep(POLL_INTERVAL)
        raise TimeoutError(f"Ark task {task_id} did not finish within {MAX_WAIT}s")

    def _download(self, url: str, output_path: str) -> None:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with requests.get(url, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    fh.write(chunk)
