"""Playground API routes — generation, history, and template management."""

import json
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File

from .models import (
    CreateTemplateRequest,
    DepthVideoRequest,
    EstimateCostRequest,
    EstimateCostResponse,
    GenerateRequest,
    OfficialDigitalCharacter,
    PlaygroundTemplate,
    SaveToLibraryRequest,
    UpdateTemplateRequest,
)
from .depth_service import DepthJobManager
from .service import PlaygroundService
from .storage import PlaygroundStorage
from ..comic_gen import auth
from ...utils import get_logger
from ...utils.media_refs import resolve_local_media_path, to_posix_media_path
from ...utils.upload_guard import save_video_upload, validate_image_upload
from ...utils.grid_overlay import apply_grid_overlay

logger = get_logger(__name__)

router = APIRouter(tags=["playground"])

# Module-level singletons — initialised when the router is first imported.
_storage = PlaygroundStorage()
_service = PlaygroundService(_storage)

# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    user=Depends(auth.require_login),
):
    """Create a generation record and kick off processing in the background."""
    gen = _service.create_generation(request, owner_id=user.id)
    background_tasks.add_task(_service.process_generation, gen.id)
    return gen


def estimate_cost(request: EstimateCostRequest, _user=Depends(auth.require_login)):
    """Pre-generation cost estimate for the given mode/model/parameters."""
    cost_usd, per_unit_cost_usd, priced = _service.estimate_cost(
        request.mode, request.model_id, request.parameters, request.batch_size or 1
    )
    return EstimateCostResponse(cost_usd=cost_usd, per_unit_cost_usd=per_unit_cost_usd, priced=priced)


router.add_api_route("/generate", generate, methods=["POST"])
router.add_api_route("/estimate-cost", estimate_cost, methods=["POST"])

# ---------------------------------------------------------------------------
# Official digital characters (Ark Digital Character Library)
# ---------------------------------------------------------------------------

OFFICIAL_CHARACTERS_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "digital_characters" / "official.json"
)


@lru_cache(maxsize=1)
def _load_official_characters() -> List[OfficialDigitalCharacter]:
    with open(OFFICIAL_CHARACTERS_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    characters = []
    for entry in data["characters"]:
        thumbnail_path = entry.pop("thumbnail_path")
        entry["thumbnail_url"] = f"/files/digital-characters/{Path(thumbnail_path).name}"
        characters.append(OfficialDigitalCharacter(**entry))
    return characters


def list_official_characters():
    """Curated BytePlus ModelArk Digital Character Library entries.

    Static, hand-verified list (not a live Ark API call) — see
    config/digital_characters/official.json for provenance."""
    return _load_official_characters()


router.add_api_route("/official-characters", list_official_characters, methods=["GET"])

# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def list_history(limit: int = 50, offset: int = 0):
    """Return paginated generation history, newest first."""
    return _storage.list_history(limit=limit, offset=offset)


def get_generation(generation_id: str):
    """Return full details for a single generation."""
    gen = _storage.get_generation(generation_id)
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found")
    return gen


def get_generation_status(generation_id: str):
    """Return lightweight status payload for polling."""
    gen = _storage.get_generation(generation_id)
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found")
    return {
        "id": gen.id,
        "status": gen.status,
        "outputs": gen.outputs,
        "error": gen.error,
    }


def delete_generation(generation_id: str):
    """Delete a generation record and its outputs."""
    if not _storage.delete_generation(generation_id):
        raise HTTPException(status_code=404, detail="Generation not found")
    return {"ok": True}


def save_to_library(
    generation_id: str,
    output_id: str,
    request: Optional[SaveToLibraryRequest] = None,
):
    """Save a specific generation output to the project library."""
    category = request.category if request else "general"
    if not _service.save_to_library(generation_id, output_id, category):
        raise HTTPException(status_code=404, detail="Generation or output not found")
    return {"ok": True}


router.add_api_route("/history", list_history, methods=["GET"])
router.add_api_route("/history/{generation_id}", get_generation, methods=["GET"])
router.add_api_route(
    "/history/{generation_id}/status", get_generation_status, methods=["GET"]
)
router.add_api_route(
    "/history/{generation_id}", delete_generation, methods=["DELETE"]
)
router.add_api_route(
    "/history/{generation_id}/outputs/{output_id}/save-to-library",
    save_to_library,
    methods=["POST"],
)

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def list_templates():
    """Return all saved prompt templates."""
    return _storage.list_templates()


def create_template(request: CreateTemplateRequest):
    """Create a new prompt template."""
    now = datetime.now(timezone.utc).isoformat()
    template = PlaygroundTemplate(
        id=str(uuid.uuid4()),
        name=request.name,
        category=request.category or "general",
        prompt=request.prompt,
        negative_prompt=request.negative_prompt,
        default_mode=request.default_mode,
        default_model_id=request.default_model_id,
        default_parameters=request.default_parameters or {},
        created_at=now,
        updated_at=now,
    )
    _storage.add_template(template)
    return template


def update_template(template_id: str, request: UpdateTemplateRequest):
    """Update an existing prompt template (partial update)."""
    template = _storage.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    update_data = request.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(template, key, value)
    template.updated_at = datetime.now(timezone.utc).isoformat()
    _storage.update_template(template)
    return template


def delete_template(template_id: str):
    """Delete a prompt template."""
    if not _storage.delete_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    return {"ok": True}


router.add_api_route("/templates", list_templates, methods=["GET"])
router.add_api_route("/templates", create_template, methods=["POST"])
router.add_api_route("/templates/{template_id}", update_template, methods=["PUT"])
router.add_api_route("/templates/{template_id}", delete_template, methods=["DELETE"])

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

UPLOAD_DIR = os.path.join("output", "playground", "uploads")


def upload_media(file: UploadFile = File(...), grid_size: int = 0, grid_color: str = "black"):
    """Upload a media file for use as playground input (reference image, first frame, etc.)."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    data, ext = validate_image_upload(file)
    data = apply_grid_overlay(data, ext, grid_size, grid_color)
    filename = f"{uuid.uuid4()}.{ext}"
    dest = os.path.join(UPLOAD_DIR, filename)
    with open(dest, "wb") as f:
        f.write(data)
    return {"path": to_posix_media_path(dest)}


def upload_video(file: UploadFile = File(...), _user=Depends(auth.require_login)):
    """Upload a reference video (the dance clip that drives motion)."""
    dest = save_video_upload(file, os.path.join(UPLOAD_DIR, str(uuid.uuid4())))
    return {"path": to_posix_media_path(dest)}


def apply_grid_to_media(path: str, grid_size: int = 0, grid_color: str = "black"):
    """Burn a grid into an existing local media file (e.g. a fresh AI generation),
    in place. Rejects anything outside output/ via resolve_local_media_path.
    """
    abs_path = resolve_local_media_path(path)
    if abs_path is None or not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Media path not found")
    ext = os.path.splitext(abs_path)[1].lstrip(".")
    with open(abs_path, "rb") as f:
        data = f.read()
    data = apply_grid_overlay(data, ext, grid_size, grid_color)
    with open(abs_path, "wb") as f:
        f.write(data)
    return {"path": to_posix_media_path(path), "has_grid_overlay": grid_size > 0}


router.add_api_route("/upload", upload_media, methods=["POST"])
router.add_api_route("/upload-video", upload_video, methods=["POST"])
router.add_api_route("/apply-grid", apply_grid_to_media, methods=["POST"])

# ---------------------------------------------------------------------------
# Depth preprocessing (local GPU) — step 2 of the dance-swap flow
# ---------------------------------------------------------------------------

_depth_jobs = DepthJobManager()


def depth_capability(_user=Depends(auth.require_login)):
    """What this machine can do, so the UI can warn before a long run."""
    return _depth_jobs.capability()


def create_depth_job(
    request: DepthVideoRequest,
    background_tasks: BackgroundTasks,
    _user=Depends(auth.require_login),
):
    """Kick off depth extraction for an already-uploaded clip."""
    if not os.path.exists(request.source_video):
        raise HTTPException(status_code=400, detail=f"找不到视频：{request.source_video}")

    job = _depth_jobs.create(request.source_video)
    background_tasks.add_task(
        _depth_jobs.run,
        job.id,
        encoder=request.encoder or "auto",
        input_size=request.input_size,
        max_seconds=request.max_seconds,
        target_fps=request.target_fps,
        contrast=request.contrast or "percentile",
    )
    return job.to_dict()


def get_depth_job(job_id: str, _user=Depends(auth.require_login)):
    job = _depth_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Depth job not found")
    return job.to_dict()


router.add_api_route("/depth/capability", depth_capability, methods=["GET"])
router.add_api_route("/depth/jobs", create_depth_job, methods=["POST"])
router.add_api_route("/depth/jobs/{job_id}", get_depth_job, methods=["GET"])
