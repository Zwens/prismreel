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
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from .base import VideoGenModel
from ..utils.oss_utils import OSSImageUploader
from ..utils.provider_media import resolve_media_input

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
    "seedance-2.5-v2v": "dreamina-seedance-2-5-260628",
}

# Editing and extension are sub-types of one omni-reference task, not separate
# models — and only 2.5 accepts the parameter that selects them. Sending it to
# a 2.0 model turns an otherwise valid task into a rejected one, so the wire id
# decides whether it goes out at all.
ARK_OMNI_TASK_TYPE_MODELS = {"dreamina-seedance-2-5-260628"}

OMNI_TASK_TYPES = ("auto", "reference", "edit", "extend")

# docs/api-reference/byteplus-ark-seedance-seedream.md §2.4
EDIT_SOURCE_MIN_SECONDS = 4
EDIT_SOURCE_MAX_SECONDS = 30

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


def probe_video_duration(src: Optional[str]) -> Optional[float]:
    """Length of a local source video in seconds, or None when it cannot be
    told cheaply.

    None is not a failure: a source living on OSS would need a download to
    probe, and Ark validates an explicit sub-type synchronously anyway. So an
    unprobeable source is passed through rather than blocked — guessing here
    would reject valid requests to avoid a round trip.
    """
    if not src or src.startswith(("http://", "https://")):
        return None
    if not os.path.exists(src):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", src],
            capture_output=True, text=True, timeout=15,
        )
        return float((out.stdout or "").strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def validate_omni_task(
    task_type: Optional[str],
    *,
    videos: List[str],
    ratio: Optional[str],
    duration: Optional[int],
    source_seconds: Optional[float],
) -> None:
    """Reject a request Ark would reject, before it is ever sent.

    Verified 2026-09-08: Ark does NOT validate these synchronously, despite the
    vendor doc saying so. A violating request gets HTTP 200 and a task id, and
    only then fails asynchronously — the failed task is free, but the user has
    waited minutes to be told a field was wrong. So this is the only check that
    can answer immediately, not a second line behind the vendor's.
    """
    if task_type is None or task_type == "auto":
        return
    if task_type not in OMNI_TASK_TYPES:
        raise ValueError(
            f"Unknown task_type {task_type!r}; expected one of {', '.join(OMNI_TASK_TYPES)}"
        )
    if task_type == "reference":
        return

    if not videos:
        raise ValueError(
            f"task_type={task_type!r} needs a source video (content role reference_video)"
        )
    if (ratio or "").strip() != "adaptive":
        raise ValueError(
            f"task_type={task_type!r} requires ratio 'adaptive', got {ratio!r}"
        )

    if task_type == "edit":
        if duration is not None and duration != -1:
            raise ValueError(
                f"task_type='edit' keeps the source length, so duration must be -1, got {duration!r}"
            )
        if source_seconds is not None and not (
            EDIT_SOURCE_MIN_SECONDS <= source_seconds <= EDIT_SOURCE_MAX_SECONDS
        ):
            raise ValueError(
                f"task_type='edit' needs a source video of "
                f"{EDIT_SOURCE_MIN_SECONDS}-{EDIT_SOURCE_MAX_SECONDS}s, got {source_seconds:.1f}s"
            )


def explain_ark_error(status_code: int, body_text: str) -> str:
    """Turn an Ark error body into a message worth showing the user.

    Ark returns structured JSON ({"error": {"code", "message", ...}}) even on
    4xx, but raise_for_status()'s default message ("400 Client Error") throws
    that away — e.g. a content-policy rejection (real-person detection in the
    reference image) reads identically to a malformed request, leaving the
    user with no idea what to actually fix.
    """
    try:
        import json as _json
        data = _json.loads(body_text) if body_text else {}
    except (ValueError, TypeError):
        data = {}

    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        code = error.get("code") or ""
        message = error.get("message") or ""
        detail = f"{code}: {message}" if code else message
        if detail:
            return f"HTTP {status_code} {detail}"

    detail = (body_text or "")[:300]
    return f"HTTP {status_code}: {detail}" if detail else f"HTTP {status_code}"


def build_ark_content(
    prompt: str,
    images: List[Tuple[str, Optional[str]]],
    flags: str,
    videos: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """The `content` array: one text item, then one image_url item per
    reference, then one video_url item per source video. Order is preserved —
    for R2V it is what the model maps to its reference slots.

    Each image carries its Ark `role` (`first_frame`, `last_frame`, or
    `reference_image`) — Ark's first-frame, first+last-frame, and
    omni-reference scenarios are mutually exclusive, so role is what tells it
    which scenario this request is.

    The video item carries role=reference_video, which is what marks it as the
    subject of an edit or extension rather than another reference.
    """
    text = " ".join(part for part in [(prompt or "").strip(), flags.strip()] if part)
    content: List[Dict[str, Any]] = [{"type": "text", "text": text}]
    for url, role in images:
        if url:
            item: Dict[str, Any] = {"type": "image_url", "image_url": {"url": url}}
            if role:
                item["role"] = role
            content.append(item)
    for url in videos or []:
        if url:
            content.append({
                "type": "video_url",
                "video_url": {"url": url},
                "role": "reference_video",
            })
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

    def _resolve_ark_image_url(self, ref: Optional[str], *, model_name: Optional[str]) -> Optional[str]:
        """Resolve a first/last-frame reference to a URL Ark can fetch.

        ``ref`` may already be a remote URL (pass through) or a local file
        path (upload to OSS and sign). Ark's `image_url.url` field only
        accepts a fetchable URL, unlike Kling's vendor path which takes
        base64."""
        if not ref:
            return None
        if ref.startswith(("http://", "https://")):
            return ref
        resolved = resolve_media_input(
            ref,
            model_name=model_name or "",
            modality="image",
            backend="byteplus",
            uploader=OSSImageUploader(),
        )
        return resolved.value

    def _resolve_ark_video_url(self, ref: Optional[str], *, model_name: Optional[str]) -> Optional[str]:
        """Resolve a source/reference clip to a URL Ark can fetch.

        Same contract as ``_resolve_ark_image_url``, and needed for the same
        reason: Ark's `video_url.url` only accepts a fetchable URL. Passing a
        local path through unresolved gets
        ``InvalidParameter: content[n].video_url.url ... invalid url`` — which
        is what happened for every locally-produced clip until this existed.
        """
        if not ref:
            return None
        if ref.startswith(("http://", "https://")):
            return ref
        resolved = resolve_media_input(
            ref,
            model_name=model_name or "",
            modality="reference_video",
            backend="byteplus",
            uploader=OSSImageUploader(),
        )
        return resolved.value

    def generate(self, prompt: str, output_path: str, img_url: Optional[str] = None,
                 img_path: Optional[str] = None, **kwargs) -> Tuple[str, float, Optional[dict]]:
        start = time.time()

        model_name = kwargs.get("model_name")
        last_frame_url = self._resolve_ark_image_url(kwargs.get("last_frame_url"), model_name=model_name)
        first_frame_url = self._resolve_ark_image_url(img_url or img_path, model_name=model_name)
        raw_ref_image_urls = kwargs.get("ref_image_urls") or []

        images: List[Tuple[str, Optional[str]]] = []
        if raw_ref_image_urls:
            # Omni reference-to-video: every image is a reference_image.
            # Mutually exclusive with first_frame/last_frame per Ark's contract.
            # Each ref may be a local upload path same as first/last frame —
            # route it through the same resolver instead of trusting it's
            # already a fetchable URL.
            seen = set()
            for raw_ref in raw_ref_image_urls:
                ref = self._resolve_ark_image_url(raw_ref, model_name=model_name)
                if ref and ref not in seen:
                    seen.add(ref)
                    images.append((ref, "reference_image"))
        elif first_frame_url:
            role = "first_frame" if last_frame_url else None
            images.append((first_frame_url, role))
            if last_frame_url:
                images.append((last_frame_url, "last_frame"))

        wire_model_id = self.resolve_model_id(model_name)
        if wire_model_id is None:
            # Fail before the network call: a None model id would otherwise
            # be POSTed straight to Ark, which wastes a round trip on an
            # opaque vendor-side 400 with no hint of which id was bad.
            raise ValueError(f"Unrecognized Seedance model id: {model_name!r}")

        # Two lists on purpose. `videos` is what Ark gets and must be fetchable
        # URLs; `raw_videos` keeps the caller's original refs so the duration
        # probe below still reads a local file directly. Probing the signed
        # OSS URL instead would make ffprobe do a network round trip for
        # something already on disk, and a probe failure silently disables the
        # edit-window check rather than enforcing it.
        raw_videos: List[str] = []
        videos: List[str] = []
        for src in [kwargs.get("video_url")] + list(kwargs.get("reference_video_urls") or []):
            if not src or src in raw_videos:
                continue
            resolved_video = self._resolve_ark_video_url(src, model_name=model_name)
            if resolved_video and resolved_video not in videos:
                raw_videos.append(src)
                videos.append(resolved_video)

        task_type = (kwargs.get("task_type") or None)
        validate_omni_task(
            task_type,
            videos=videos,
            ratio=kwargs.get("aspect_ratio"),
            duration=kwargs.get("duration"),
            source_seconds=probe_video_duration(raw_videos[0]) if raw_videos else None,
        )

        flags = build_param_flags(
            resolution=kwargs.get("resolution"),
            duration=kwargs.get("duration"),
            ratio=kwargs.get("aspect_ratio"),
            watermark=kwargs.get("watermark"),
        )
        body = {
            "model": wire_model_id,
            "content": build_ark_content(prompt, images, flags, videos),
        }
        # "auto" is the vendor default; spelling it out adds a field for no
        # behaviour, and 2.0 rejects the field outright.
        if task_type and task_type != "auto" and wire_model_id in ARK_OMNI_TASK_TYPE_MODELS:
            body["omni_reference_task_type"] = task_type

        url = self._tasks_url()
        logger.info("[BytePlus/Seedance] POST %s model=%s images=%d",
                    url, body["model"], len(images))
        resp = requests.post(url, json=body, headers=self._headers(), timeout=60)
        if not resp.ok:
            raise RuntimeError(
                f"Ark task create failed — {explain_ark_error(resp.status_code, resp.text)}"
            )
        task_id = (resp.json() or {}).get("id")
        if not task_id:
            raise RuntimeError(f"Ark task create returned no id: {resp.text[:300]}")

        video_url, usage = self._poll(task_id)
        self._download(video_url, output_path)

        elapsed = time.time() - start
        logger.info("[BytePlus/Seedance] done in %.1fs -> %s", elapsed, output_path)
        return output_path, elapsed, usage

    def _poll(self, task_id: str) -> Tuple[str, Optional[dict]]:
        url = f"{self._tasks_url()}/{task_id}"
        deadline = time.time() + MAX_WAIT
        while time.time() < deadline:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            if not resp.ok:
                raise RuntimeError(
                    f"Ark task poll failed — {explain_ark_error(resp.status_code, resp.text)}"
                )
            data = resp.json() or {}
            status = data.get("status")
            if status == "succeeded":
                video_url = ((data.get("content") or {}).get("video_url"))
                if not video_url:
                    raise RuntimeError(f"Ark task succeeded without a video url: {data}")
                return video_url, data.get("usage")
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
