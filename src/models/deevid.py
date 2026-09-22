"""DeeVid video generation model adapter.

API: https://api.deevid.ai/v1/open-api
Auth: Bearer token via DEEVID_API_KEY
Model: "Quality V4.0" only (image-to-video, "start_image" category)

Endpoints (confirmed 2026-09-21 against the account's own API via a real
GET /v1/open-api/image-video/models call — the original design's
"Quality V4.7" does not exist in DeeVid's system; see Task 2 Global
Constraints correction note in
docs/superpowers/plans/2026-09-21-deevid-quality-v4-7-credit-quota.md):
  upload -> POST /file-upload/upload/image (multipart, field "file") -> userImageId
  submit -> POST /image-video/start-image/task/submit (body uses userImageId, not a URL)
  status -> GET  /task/status?taskId=<id>
"""

import ipaddress
import logging
import os
import socket
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import requests

from .base import VideoGenModel
from ..utils.endpoints import get_provider_base_url
from ..utils.oss_utils import OSSImageUploader
from ..utils.provider_media import resolve_media_input

logger = logging.getLogger(__name__)

MODEL_NAME = "Quality V4.0"
RESOLUTION = "720p"
MIN_DURATION = 4
MAX_DURATION = 15


def _validate_outbound_url(url: str) -> None:
    """Reject URLs that could be used to make this server issue an SSRF
    request to internal/private infrastructure (e.g. cloud metadata
    endpoints, localhost, or private network ranges).

    This is input validation only -- it does not defend against DNS
    rebinding (resolving to a public IP at check time, then to a private
    IP at request time), which is a separate, more advanced threat model
    intentionally out of scope here.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Rejected outbound URL (unsupported scheme {parsed.scheme!r}): {url}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Rejected outbound URL (no hostname): {url}")

    if hostname.lower() == "localhost":
        raise ValueError(f"Rejected outbound URL (localhost): {url}")

    try:
        resolved_ip = socket.gethostbyname(hostname)
    except socket.gaierror as exc:
        raise ValueError(f"Rejected outbound URL (cannot resolve host {hostname!r}): {url}") from exc

    ip = ipaddress.ip_address(resolved_ip)
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        raise ValueError(
            f"Rejected outbound URL (host {hostname!r} resolves to internal address {resolved_ip}): {url}"
        )


class DeeVidModel(VideoGenModel):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key") or os.getenv("DEEVID_API_KEY", "")
        self.last_task_id: Optional[str] = None

    def _headers(self, json_content: bool = True) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if json_content:
            headers["Content-Type"] = "application/json"
        return headers

    def _resolve_image_url(self, img_url: Optional[str], img_path: Optional[str]) -> str:
        ref = img_url if (isinstance(img_url, str) and img_url.startswith(("http://", "https://"))) else (img_path or img_url)
        if not ref:
            raise ValueError("DeeVid image-to-video requires img_path or img_url")
        resolved = resolve_media_input(
            ref,
            model_name="deevid/quality-v4.0",
            modality="image",
            backend="vendor",
            uploader=OSSImageUploader(),
        )
        return resolved.value

    def _upload_image(self, base_url: str, image_url: str) -> int:
        """Download the resolved image and re-upload it to DeeVid's own
        file-upload endpoint, returning the userImageId the submit API needs."""
        _validate_outbound_url(image_url)
        image_bytes = requests.get(image_url, timeout=60).content
        upload_url = f"{base_url}/file-upload/upload/image"
        resp = requests.post(
            upload_url,
            headers=self._headers(json_content=False),
            files={"file": ("input.png", image_bytes)},
            timeout=60,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"DeeVid image upload failed (HTTP {resp.status_code}): {resp.text}")
        data = resp.json()
        user_image_id = (data.get("data") or {}).get("userImageId")
        if user_image_id is None:
            raise RuntimeError(f"No userImageId in DeeVid upload response: {data}")
        return user_image_id

    def generate(
        self,
        prompt: str,
        output_path: str,
        img_url: str = None,
        img_path: str = None,
        duration: int = 5,
        **kwargs,
    ) -> Tuple[str, float]:
        duration = max(MIN_DURATION, min(MAX_DURATION, int(duration)))
        start_time = time.time()
        base_url = get_provider_base_url("DEEVID")

        image_url = self._resolve_image_url(img_url, img_path)
        user_image_id = self._upload_image(base_url, image_url)

        submit_url = f"{base_url}/image-video/start-image/task/submit"
        body = {
            "model": MODEL_NAME,
            "prompt": prompt or "",
            "userImageId": user_image_id,
            "resolution": RESOLUTION,
            "duration": duration,
        }
        logger.info("[DeeVid] Submitting i2v task (duration=%ss)", duration)
        resp = requests.post(submit_url, headers=self._headers(), json=body, timeout=30)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"DeeVid submission failed (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        task_id = str((data.get("data") or {}).get("taskId") or "")
        if not task_id:
            raise RuntimeError(f"No taskId in DeeVid response: {data}")
        self.last_task_id = task_id

        status_url = f"{base_url}/task/status"
        max_wait = 600
        poll_interval = 10
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                status_resp = requests.get(
                    status_url, headers=self._headers(),
                    params={"taskId": task_id}, timeout=30,
                )
            except requests.RequestException as exc:
                logger.warning("[DeeVid] Poll request failed (%s); retrying (task %s)", exc, task_id)
                continue

            if status_resp.status_code != 200:
                logger.warning("[DeeVid] Poll returned HTTP %s", status_resp.status_code)
                continue

            status_data = (status_resp.json().get("data")) or {}
            status = (status_data.get("status") or "").upper()
            logger.info("[DeeVid] Task %s status: %s (%ss)", task_id, status, elapsed)

            if status == "SUCCESS":
                video_url = status_data.get("resultVideoUrl")
                if not video_url:
                    raise RuntimeError(f"DeeVid task {task_id} succeeded but has no resultVideoUrl: {status_data}")
                _validate_outbound_url(video_url)
                video_content = requests.get(video_url, timeout=120).content
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(video_content)
                generation_time = time.time() - start_time
                logger.info("[DeeVid] Done in %.1fs -> %s", generation_time, output_path)
                return output_path, generation_time

            if status == "FAILED":
                raise RuntimeError(f"DeeVid task {task_id} failed: {status_data}")

        raise RuntimeError(f"DeeVid task {task_id} timed out after {max_wait}s")
