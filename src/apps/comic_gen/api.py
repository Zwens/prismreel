# ─────────────────────────────────────────────────────────────────────────────
# IMPORTANT — handler async/sync convention (audited 2026-05-21):
#
# DEFAULT every new endpoint to `def`, NOT `async def`.
#
# FastAPI's contract:
#   - `async def` handlers run on the asyncio event loop. If the body does any
#     blocking I/O (sync HTTP call, json.dump, requests.post, openai sync
#     client, ffmpeg via subprocess.run, etc.) it FREEZES every other request
#     until the blocking call returns — including unrelated GETs the modal
#     uses to load config. Symptom: "modal stuck on 加载配置中...".
#   - `def` handlers get auto-dispatched to anyio's threadpool, so blocking
#     I/O doesn't touch the event loop. Concurrent requests stay responsive.
#
# Use `async def` ONLY when the body has `await` (streaming uploads, real
# asyncio primitives, awaiting `call_next` in middleware, asyncio.to_thread).
#
# The 7 legitimate async endpoints (verified to use await): middleware
# add_cache_control_header, create_project, reparse_project,
# import_file_preview, import_file_confirm, upload_t2i_frame,
# analyze_script_for_styles. All others are `def` for a reason.
# ─────────────────────────────────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, Dict, List, Any
import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import json
import os
import uuid
import logging
import traceback
from .pipeline import ComicGenPipeline, LibraryAssetInUseError
from .models import (
    ArtDirection,
    PromptConfig,
    Script,
    Series,
    StoryboardFrame,
    VideoTask,
)
from .llm import ScriptProcessor, DEFAULT_STORYBOARD_POLISH_PROMPT, DEFAULT_VIDEO_POLISH_PROMPT, DEFAULT_R2V_POLISH_PROMPT, DEFAULT_ENTITY_EXTRACTION_PROMPT, DEFAULT_STYLE_ANALYSIS_PROMPT, DEFAULT_STORYBOARD_EXTRACTION_PROMPT
from ...utils.oss_utils import OSSImageUploader, sign_oss_urls_in_data
from ...utils import setup_logging
from ...utils.upload_guard import validate_image_upload
from ...utils.grid_overlay import apply_grid_overlay
from ...utils.rate_limit import is_rate_limited
from fastapi.responses import JSONResponse
from dotenv import load_dotenv, set_key

app = FastAPI(title="AI Comic Gen API")
logger = logging.getLogger(__name__)

# Setup logging to user directory
setup_logging()

# Use absolute path for .env file (api.py is in src/apps/comic_gen/)
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
env_path = os.path.join(_project_root, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)

# auth and playground router import AFTER .env is loaded — auth.py reads
# JWT_SECRET at module scope, so importing it before load_dotenv() caches an
# empty secret in clean environments (see memory: JWT_SECRET import order bug)
from . import auth, user_repo
from ..playground.api import router as playground_router
app.include_router(playground_router, prefix="/playground")

# Debug: Print OSS configuration at startup
logger.info(f"STARTUP: OSS_ENDPOINT={os.getenv('OSS_ENDPOINT')}, OSS_BUCKET_NAME={os.getenv('OSS_BUCKET_NAME')}, OSS_BASE_PATH={os.getenv('OSS_BASE_PATH')}")



_cors_origins_env = os.getenv("PRISMREEL_CORS_ORIGINS", "").strip()
_cors_allow_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()] if _cors_origins_env else ["*"]

# The login cookie (Task 9/10) needs allow_credentials=True to cross the
# frontend<->backend port gap in `next dev` — but that's incompatible with
# allow_origins=["*"] by browser spec, so with no explicit allowlist we fall
# back to a localhost-only regex (any port) instead of leaving credentialed
# requests silently dropped in the default dev setup.
_cors_allow_credentials = bool(_cors_origins_env)
_cors_allow_origin_regex = None
if not _cors_origins_env:
    _cors_allow_origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    _cors_allow_credentials = True

# `Secure` cookies are only stored by browsers over HTTPS. Same dev/prod
# signal as the CORS block above: no explicit PRISMREEL_CORS_ORIGINS means
# local `next dev` over plain http, where Secure=True would silently drop
# the login cookie on every request.
_cookie_secure = bool(_cors_origins_env)

# --- API key gate ---
# Set PRISMREEL_API_KEY to require this header on every request except the
# paths below. Unset (desktop/local dev default) = no gate, matches prior
# behavior so `python main.py` on 127.0.0.1 keeps working unauthenticated.
_API_KEY = os.getenv("PRISMREEL_API_KEY", "").strip()
_API_KEY_EXEMPT_PREFIXES = ("/health", "/files/", "/static/", "/docs", "/openapi.json", "/redoc")

@app.middleware("http")
async def enforce_api_key(request: Request, call_next):
    if _API_KEY and not request.url.path.startswith(_API_KEY_EXEMPT_PREFIXES):
        if request.headers.get("x-api-key") != _API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid API key"})
    return await call_next(request)

_AUTH_PUBLIC_PREFIXES = ("/health", "/files/", "/static/", "/docs", "/openapi.json", "/redoc", "/auth/login", "/auth/redeem_invite")


@app.middleware("http")
async def enforce_login(request: Request, call_next):
    if not auth.JWT_SECRET:
        return await call_next(request)
    path = request.url.path
    if path.startswith(_AUTH_PUBLIC_PREFIXES):
        return await call_next(request)
    user = auth.get_current_user_from_cookie(request)
    if user is None or not user.is_active:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return await call_next(request)

# --- Rate limit for AI-cost-triggering generation endpoints ---
# Every /generate_* or .../generate call fans out to a paid vendor API
# (DashScope/Kling/Vidu/Ark), so this caps spend-per-caller, not just load.
_GENERATION_RATE_LIMIT_MAX = int(os.getenv("PRISMREEL_GENERATION_RATE_LIMIT", "20"))
_GENERATION_RATE_LIMIT_WINDOW_S = 60.0

@app.middleware("http")
async def rate_limit_generation_endpoints(request: Request, call_next):
    if request.method == "POST" and "generate" in request.url.path:
        client_key = request.headers.get("x-api-key") or (request.client.host if request.client else "unknown")
        if is_rate_limited(client_key, _GENERATION_RATE_LIMIT_MAX, _GENERATION_RATE_LIMIT_WINDOW_S):
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: max {_GENERATION_RATE_LIMIT_MAX} generation calls per {int(_GENERATION_RATE_LIMIT_WINDOW_S)}s"},
            )
    return await call_next(request)

# Middleware to add cache headers to static files
@app.middleware("http")
async def add_cache_control_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/files/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    return response

# Create output directory if it doesn't exist
os.makedirs("output", exist_ok=True)
os.makedirs("output/uploads", exist_ok=True)
os.makedirs("output/video", exist_ok=True)
os.makedirs("output/assets", exist_ok=True)

# BGM presets: the mux code path is complete but silently skips when the
# audio file is absent, which used to make every export silent. Warn loudly.
try:
    from .audio import install_bundled_bgm_presets, verify_bgm_assets

    # In a packaged build the mp3s arrive under sys._MEIPASS, but every
    # lookup is relative to the CWD (main.py chdir()s to ~/.prismreel), so
    # they have to be seeded into output/ first or the check below would
    # correctly report all eight as missing on every desktop install.
    install_bundled_bgm_presets()

    _missing_bgm = verify_bgm_assets()
    if _missing_bgm:
        logger.warning(
            f"[STARTUP] {len(_missing_bgm)} BGM preset file(s) missing — "
            f"exports using them will have no background music: {_missing_bgm}"
        )
except Exception as e:  # never block startup on a cosmetic check
    logger.warning(f"[STARTUP] BGM asset verification skipped: {e}")

# Official Digital Character Library thumbnails (local copies -- BytePlus
# serves these via 12-hour signed URLs, so they're downloaded once and
# committed rather than proxied live). See config/digital_characters/official.json.
# Must be registered before the broad "/files" mount below -- Starlette's
# Mount matching is registration-order, not longest-prefix, so a later,
# more specific mount is unreachable once a broader one already claims the
# prefix (verified: the broader mount's own 404 wins, the router never
# falls through to try the next candidate).
os.makedirs("config/digital_characters/thumbnails", exist_ok=True)
app.mount(
    "/files/digital-characters",
    StaticFiles(directory="config/digital_characters/thumbnails"),
    name="files_digital_characters",
)

# Mount static files with multiple aliases to handle plural/singular inconsistencies
# Legacy paths in projects.json often use 'outputs/videos' or 'outputs/assets'
app.mount("/files/outputs/videos", StaticFiles(directory="output/video"), name="files_outputs_videos")
app.mount("/files/outputs/assets", StaticFiles(directory="output/assets"), name="files_outputs_assets")
app.mount("/files/outputs", StaticFiles(directory="output"), name="files_outputs")
app.mount("/files/videos", StaticFiles(directory="output/video"), name="files_videos")
app.mount("/files/assets", StaticFiles(directory="output/assets"), name="files_assets")
app.mount("/files", StaticFiles(directory="output"), name="files")

os.makedirs("output/users", exist_ok=True)
app.mount("/files/users", StaticFiles(directory="output/users"), name="files_users")


@app.middleware("http")
async def enforce_file_ownership(request: Request, call_next):
    path = request.url.path
    if path.startswith("/files/users/"):
        parts = path.split("/")
        # ["", "files", "users", "{owner_id}", "{project_id}", ...]
        if len(parts) >= 4:
            owner_id = parts[3]
            user = auth.get_current_user_from_cookie(request)
            if not user or (user.role != "admin" and user.id != owner_id):
                return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)

# CORSMiddleware must be added last: Starlette's middleware stack executes
# in reverse-registration order, so the most-recently-added middleware runs
# outermost. Every @app.middleware("http") function above can short-circuit
# with a 401/403/429 response (enforce_login, enforce_api_key,
# enforce_file_ownership, rate_limit_generation_endpoints) — those responses
# must still pass through CORSMiddleware or the browser drops them entirely
# for lacking an Access-Control-Allow-Origin header before axios ever sees
# the status code.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins if _cors_origins_env else [],
    allow_origin_regex=_cors_allow_origin_regex,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # Allow browsers to access Content-Disposition for downloads
)

# Ensure playground output directories exist
os.makedirs("output/playground/images", exist_ok=True)
os.makedirs("output/playground/videos", exist_ok=True)
app.mount("/files/playground", StaticFiles(directory="output/playground"), name="files_playground")

# Initialize pipeline
pipeline = ComicGenPipeline()


# ─────────────────────────────────────────────────────────────────────
# Multi-tenant auth — /auth/* (public) and /admin/* (admin-only)
# ─────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str


class RedeemInviteRequest(BaseModel):
    invite_code: str
    email: str
    password: str


class CreateInviteRequest(BaseModel):
    role: str = "member"
    email_hint: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    new_password: str


def get_owned_script(script_id: str, user=Depends(auth.require_login)):
    script = pipeline.get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Project not found")
    if user.role != "admin" and script.owner_id and script.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return script


def get_owned_series(series_id: str, user=Depends(auth.require_login)):
    series = pipeline.get_series(series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    if user.role != "admin" and series.owner_id and series.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Series not found")
    return series


@app.post("/auth/login")
def login(body: LoginRequest):
    user = user_repo.get_user_by_email(body.email)
    if not user or not user.is_active or not auth.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    token = auth.create_access_token(user.id, user.role)
    resp = JSONResponse({"id": user.id, "email": user.email, "role": user.role, "display_name": user.display_name})
    resp.set_cookie(
        "access_token", token,
        httponly=True, secure=_cookie_secure, samesite="lax",
        max_age=auth.JWT_EXPIRE_DAYS * 86400,
    )
    return resp


@app.post("/auth/logout")
def logout(_user=Depends(auth.require_login)):
    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie("access_token")
    return resp


@app.get("/auth/me")
def auth_me(user=Depends(auth.require_login)):
    return {"id": user.id, "email": user.email, "role": user.role, "display_name": user.display_name}


@app.post("/auth/redeem_invite")
def redeem_invite(body: RedeemInviteRequest):
    try:
        user = user_repo.redeem_invite(body.invite_code, body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = auth.create_access_token(user.id, user.role)
    resp = JSONResponse({"id": user.id, "email": user.email, "role": user.role})
    resp.set_cookie(
        "access_token", token,
        httponly=True, secure=_cookie_secure, samesite="lax",
        max_age=auth.JWT_EXPIRE_DAYS * 86400,
    )
    return resp


@app.post("/admin/invites")
def admin_create_invite(body: CreateInviteRequest, admin=Depends(auth.require_admin)):
    code = user_repo.create_invite(created_by=admin.id, role=body.role, email_hint=body.email_hint)
    return {"invite_code": code}


@app.get("/admin/users")
def admin_list_users(_admin=Depends(auth.require_admin)):
    return [
        {"id": u.id, "email": u.email, "role": u.role, "display_name": u.display_name, "is_active": u.is_active, "created_at": u.created_at}
        for u in user_repo.list_users()
    ]


@app.post("/admin/users/{user_id}/reset_password")
def admin_reset_password(user_id: str, body: ResetPasswordRequest, _admin=Depends(auth.require_admin)):
    if not user_repo.get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    user_repo.set_password(user_id, body.new_password)
    return {"status": "password_reset"}


@app.post("/admin/users/{user_id}/deactivate")
def admin_deactivate_user(user_id: str, _admin=Depends(auth.require_admin)):
    if not user_repo.get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    user_repo.set_active(user_id, False)
    return {"status": "deactivated"}


@app.get("/usage/me")
def get_my_usage(user=Depends(auth.require_login)):
    from . import usage_repo
    return {"user_id": user.id, "summary": usage_repo.get_user_usage_summary(user.id)}


@app.get("/usage/deevid-credits")
def get_deevid_credits(user=Depends(auth.require_login)):
    from datetime import datetime, timezone
    from . import credit_ledger

    now_ts = time.time()
    start, end = credit_ledger.current_period(now_ts)
    remaining = credit_ledger.get_remaining_points(now_ts)
    used = credit_ledger.TOTAL_POINTS_PER_PERIOD - remaining

    return {
        "used": used,
        "remaining": remaining,
        "total": credit_ledger.TOTAL_POINTS_PER_PERIOD,
        "period_start": datetime.fromtimestamp(start, tz=timezone.utc).strftime("%Y-%m-%d"),
        "period_end": datetime.fromtimestamp(end, tz=timezone.utc).strftime("%Y-%m-%d"),
    }


@app.get("/admin/usage")
def admin_get_all_usage(_admin=Depends(auth.require_admin)):
    from . import usage_repo
    return usage_repo.get_all_users_usage_summary()


@app.get("/debug/config")
def debug_config():
    """Diagnostic endpoint to check OSS and path configuration."""
    uploader = OSSImageUploader()
    return {
        "oss_configured": uploader.is_configured,
        "oss_bucket_initialized": uploader.bucket is not None,
        "oss_base_path": os.getenv("OSS_BASE_PATH", "prismreel"),
        "output_dir_exists": os.path.exists("output"),
        "output_contents": os.listdir("output") if os.path.exists("output") else [],
        "cwd": os.getcwd(),
        "env_vars_present": {
            "OSS_ENDPOINT": bool(os.getenv("OSS_ENDPOINT")),
            "OSS_BUCKET_NAME": bool(os.getenv("OSS_BUCKET_NAME")),
            "ALIBABA_CLOUD_ACCESS_KEY_ID": bool(os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")),
        }
    }

def signed_response(data):
    """Helper to sign OSS URLs in data before returning to frontend.
    
    Handles Pydantic models, lists of models, and dicts.
    Returns a JSONResponse with signed URLs.
    """
    if data is None:
        return JSONResponse(content=None)
    
    # Convert Pydantic models to dict
    if hasattr(data, "model_dump"):
        processed_data = data.model_dump()
    elif isinstance(data, list):
        processed_data = [item.model_dump() if hasattr(item, "model_dump") else item for item in data]
    else:
        processed_data = data
    
    # Check if OSS is configured
    uploader = OSSImageUploader()
    if uploader.is_configured:
        # OSS mode: sign URLs in the data
        processed_data = sign_oss_urls_in_data(processed_data, uploader)
    
    # Return JSONResponse directly to avoid Pydantic re-validation stripping fields
    return JSONResponse(content=processed_data)


# ============================================================
# Shared Request Models (used by both Project and Series endpoints)
# ============================================================

class GenerateAssetRequest(BaseModel):
    asset_id: str
    asset_type: str
    style_preset: str = "Cinematic"
    reference_image_url: Optional[str] = None
    style_prompt: Optional[str] = None
    generation_type: str = "all"  # 'full_body', 'three_view', 'headshot', 'all', 'reference_sheet'
    prompt: Optional[str] = None
    apply_style: bool = True
    negative_prompt: Optional[str] = None
    batch_size: int = 1
    model_name: Optional[str] = None
    aspect_ratio: Optional[str] = None

class ToggleLockRequest(BaseModel):
    asset_id: str
    asset_type: str

class UpdateAssetImageRequest(BaseModel):
    asset_id: str
    asset_type: str
    image_url: str

class UpdateAssetAttributesRequest(BaseModel):
    asset_id: str
    asset_type: str
    attributes: Dict[str, Any]


@app.get("/health")
def health_check():
    """Lightweight liveness probe used by the Diagnose UI on stuck
    tasks and by external uptime checks. Intentionally cheap: no DB
    hit, no provider call, just a 200 + a few facts the frontend can
    show next to the spinner ("backend reachable, log file at X")."""
    from ...utils import get_log_dir
    log_dir = get_log_dir()
    log_file = os.path.join(log_dir, "app.log")
    return {
        "ok": True,
        "time": time.time(),
        "log_file": log_file,
        "log_dir": log_dir,
        "studio_projects": len(getattr(pipeline, "scripts", {})),
    }


@app.get("/diagnose/log_tail")
def diagnose_log_tail(lines: int = 200):
    """Return the last N lines of the app log + an ERROR/Exception
    summary so the Diagnose UI on stuck tasks can show actual log
    content instead of just a path. Read-only, capped to 1000 lines so
    a runaway client can't hose the process."""
    from ...utils import get_log_dir
    capped = max(1, min(int(lines or 200), 1000))
    log_path = os.path.join(get_log_dir(), "app.log")
    if not os.path.exists(log_path):
        return {"path": log_path, "lines": [], "errors": [], "missing": True}
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            # Read all, then tail. App.log is bounded by the rotating
            # handler (≤ 5 MB active) so this is safe.
            all_lines = f.readlines()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not read log: {exc}")
    tail = all_lines[-capped:] if len(all_lines) > capped else all_lines
    error_keywords = ("ERROR", "Exception", "Failed", "Unauthorized", "Traceback")
    errors = [
        ln.rstrip("\n")
        for ln in tail
        if any(k in ln for k in error_keywords)
    ][-30:]
    return {
        "path": log_path,
        "total_lines": len(all_lines),
        "returned_lines": len(tail),
        "lines": [ln.rstrip("\n") for ln in tail],
        "errors": errors,
        "missing": False,
    }


@app.get("/system/check")
def check_system():
    """Check system dependencies (ffmpeg, etc.) and configuration."""
    from ...utils.system_check import run_system_checks
    return run_system_checks()





@app.post("/upload")
def upload_file(file: UploadFile = File(...), grid_size: int = 0, grid_color: str = "black"):
    """Uploads a file and returns its URL (OSS if configured, else local)."""
    try:
        data, ext = validate_image_upload(file)
        data = apply_grid_overlay(data, ext, grid_size, grid_color)
        filename = f"{uuid.uuid4()}.{ext}"
        file_path = os.path.join("output/uploads", filename)

        with open(file_path, "wb") as buffer:
            buffer.write(data)

        has_grid_overlay = grid_size > 0

        # Try uploading to OSS
        oss_url = OSSImageUploader().upload_image(file_path)
        if oss_url:
            return signed_response({"url": oss_url, "has_grid_overlay": has_grid_overlay})

        # Fallback to local URL (relative path for frontend getAssetUrl)
        return {"url": f"uploads/{filename}", "has_grid_overlay": has_grid_overlay}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UploadAssetRequest(BaseModel):
    upload_type: str  # "full_body" | "head_shot" | "three_views" | "image"
    description: Optional[str] = None  # User-modified description for reverse generation


@app.post("/projects/{script_id}/assets/{asset_type}/{asset_id}/upload")
def upload_asset(
    asset_type: str,
    asset_id: str,
    upload_type: str,
    description: Optional[str] = None,
    grid_size: int = 0,
    grid_color: str = "black",
    file: UploadFile = File(...),
    script: Script = Depends(get_owned_script),
):
    """
    Uploads an image as a new variant for an asset.
    The uploaded image is marked as the 'upload source' for reverse generation.

    - asset_type: "character", "scene", or "prop"
    - upload_type: "full_body", "head_shot", "three_views", or "image" (for scene/prop)
    - description: Optional modified description for the asset
    - grid_size: 0 (original) or 6 — burns an evenly-spaced grid into the photo
    - grid_color: "black" or "white"
    """
    script_id = script.id
    try:
        # 1. Save file locally first
        data, ext = validate_image_upload(file)
        data = apply_grid_overlay(data, ext, grid_size, grid_color)
        filename = f"{uuid.uuid4()}.{ext}"
        file_path = os.path.join("output/uploads", filename)

        with open(file_path, "wb") as buffer:
            buffer.write(data)

        # 2. Upload to OSS
        uploader = OSSImageUploader()
        oss_url = uploader.upload_image(file_path)
        if not oss_url:
            oss_url = f"uploads/{filename}"  # Fallback to local path

        # 3. Update asset with new variant
        updated_script = pipeline.add_uploaded_asset_variant(
            script_id=script_id,
            asset_type=asset_type,
            asset_id=asset_id,
            upload_type=upload_type,
            image_url=oss_url,
            description=description,
            has_grid_overlay=grid_size > 0,
        )
        
        if not updated_script:
            raise HTTPException(status_code=404, detail="Script or asset not found")
        
        return signed_response(merged_project_payload(updated_script))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error uploading asset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CreateProjectRequest(BaseModel):
    title: str
    text: str
    workflow_mode: str = "r2v"  # "r2v" (default) or "i2v_legacy"
    # Optional series binding (T9). When set, the new project is created as
    # the next episode of this series (episode_number = current max + 1).
    # Omit for a standalone project — behavior unchanged.
    series_id: Optional[str] = None


@app.post("/projects", response_model=Script)
async def create_project(request: CreateProjectRequest, skip_analysis: bool = False, user=Depends(auth.require_login)):
    """Creates a new project from a novel text.

    When `series_id` is provided the project is bound as the next episode
    of that series; omitting it keeps the standalone-project behavior
    unchanged.
    """
    # Run in thread pool to avoid blocking event loop during LLM analysis (Python 3.8 compatible)
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,  # Use default executor
            partial(pipeline.create_project, request.title, request.text, skip_analysis, request.workflow_mode, request.series_id, user.id)
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return signed_response(result)



class ReparseProjectRequest(BaseModel):
    text: str


class UpdateScriptTextRequest(BaseModel):
    text: str


@app.put("/projects/{script_id}/text")
def update_script_text(request: UpdateScriptTextRequest, script: Script = Depends(get_owned_script)):
    """Persist `original_text` without re-parsing entities.

    Used by ScriptProcessor's onBlur so typing survives reload/navigation
    without triggering an LLM round-trip. Heavy reparse stays bound to the
    explicit "提取实体" CTA.
    """
    script.original_text = request.text or ""
    script.updated_at = time.time()
    pipeline._save_data()
    return signed_response(merged_project_payload(script))


@app.put("/projects/{script_id}/reparse")
async def reparse_project(request: ReparseProjectRequest, script: Script = Depends(get_owned_script)):
    """Re-parses the text for an existing project, replacing all entities."""
    try:
        # Run the blocking LLM call in a thread pool to avoid blocking the event loop (Python 3.8 compatible)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,  # Use default executor
            partial(pipeline.reparse_project, script.id, request.text)
        )
        return signed_response(merged_project_payload(result))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/projects/{script_id}/extract_preview")
async def extract_preview(request: ReparseProjectRequest, script: Script = Depends(get_owned_script)):
    """Dry-run entity extraction — returns entities without saving."""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(pipeline.extract_preview, script.id, request.text)
        )
        return {
            "characters": [c.dict() for c in result.characters],
            "scenes": [s.dict() for s in result.scenes],
            "props": [p.dict() for p in result.props],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/projects/", response_model=List[dict])
def list_projects(user=Depends(auth.require_login)):
    """Lists all projects from backend storage."""
    scripts = list(pipeline.scripts.values())
    if user.role != "admin":
        scripts = [s for s in scripts if not s.owner_id or s.owner_id == user.id]
    return signed_response(scripts)


@app.post("/projects/{script_id}/toggle_starred")
def toggle_project_starred(_owned: Script = Depends(get_owned_script)):
    """Toggle the user-starred (featured shortlist) flag on a project."""
    try:
        script = pipeline.toggle_project_starred(_owned.id)
        return signed_response(merged_project_payload(script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Series CRUD
# ============================================================

class CreateSeriesRequest(BaseModel):
    title: str
    description: str = ""
    workflow_mode: str = "r2v"
    # R2V v2 Phase 6 — content mode (scripted | freeform), defaults
    # scripted (traditional script-first flow).
    content_mode: str = "scripted"
    # PR-3e (r2v-workflow-v3) — Visual control preference.
    # 'r2v' (节奏优先, default) | 'i2v' (画面优先).
    default_generation_mode: str = "r2v"


class UpdateSeriesRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    workflow_mode: Optional[str] = None
    content_mode: Optional[str] = None
    default_generation_mode: Optional[str] = None
    # R2V v2: series-level art_direction baseline (Phase 2). Inherits +
    # override flows at the episode level read this as the source of truth.
    art_direction: Optional[ArtDirection] = None


@app.post("/series")
def create_series(request: CreateSeriesRequest, user=Depends(auth.require_login)):
    """Create a new Series."""
    series = pipeline.create_series(
        request.title,
        request.description,
        request.workflow_mode,
        request.content_mode,
        request.default_generation_mode,
        owner_id=user.id,
    )
    return signed_response(series)


@app.get("/series")
def list_series(user=Depends(auth.require_login)):
    """List all Series."""
    series_list = pipeline.list_series()
    if user.role != "admin":
        series_list = [s for s in series_list if not s.owner_id or s.owner_id == user.id]
    return signed_response(series_list)


@app.get("/series/{series_id}")
def get_series(series: Series = Depends(get_owned_series)):
    """Get Series details including assets and episode list."""
    series_id = series.id
    # Include episode summaries
    episodes = pipeline.get_series_episodes(series_id)
    result = series.model_dump()
    result["episodes"] = [
        {
            "id": ep.id,
            "title": ep.title,
            "episode_number": ep.episode_number,
            "created_at": ep.created_at,
            "updated_at": ep.updated_at,
        }
        for ep in episodes
    ]
    return signed_response(result)


@app.put("/series/{series_id}")
def update_series(request: UpdateSeriesRequest, _owned: Series = Depends(get_owned_series)):
    """Update Series fields. Uses `exclude_unset=True` so explicitly-null
    values (e.g. `{"art_direction": null}` to clear baseline) are honored,
    while fields the client didn't send remain untouched."""
    try:
        updates = request.model_dump(exclude_unset=True)
        series = pipeline.update_series(_owned.id, updates)
        return signed_response(series)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/series/{series_id}")
def delete_series(_owned: Series = Depends(get_owned_series)):
    """Delete a Series and disassociate its episodes."""
    try:
        pipeline.delete_series(_owned.id)
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class AddEpisodeRequest(BaseModel):
    script_id: str
    episode_number: Optional[int] = None


@app.post("/series/{series_id}/episodes")
def add_episode_to_series(request: AddEpisodeRequest, _owned: Series = Depends(get_owned_series)):
    """Add an existing project as an episode to a Series."""
    try:
        series = pipeline.add_episode_to_series(_owned.id, request.script_id, request.episode_number)
        return signed_response(series)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/series/{series_id}/episodes/{script_id}")
def remove_episode_from_series(script_id: str, _owned: Series = Depends(get_owned_series)):
    """Remove an episode from a Series (does not delete the project)."""
    try:
        series = pipeline.remove_episode_from_series(_owned.id, script_id)
        return signed_response(series)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/series/{series_id}/episodes")
def get_series_episodes(_owned: Series = Depends(get_owned_series)):
    """Get all episodes in a Series."""
    try:
        episodes = pipeline.get_series_episodes(_owned.id)
        return signed_response(episodes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/series/{series_id}/prompt_config")
def get_series_prompt_config(series: Series = Depends(get_owned_series)):
    """Get Series prompt config with system defaults."""
    return {
        "prompt_config": series.prompt_config.model_dump(),
        "defaults": {
            "storyboard_polish": DEFAULT_STORYBOARD_POLISH_PROMPT,
            "video_polish": DEFAULT_VIDEO_POLISH_PROMPT,
            "r2v_polish": DEFAULT_R2V_POLISH_PROMPT,
            "storyboard_extraction": DEFAULT_STORYBOARD_EXTRACTION_PROMPT,
        },
    }


@app.put("/series/{series_id}/prompt_config")
def update_series_prompt_config(config: PromptConfig, _owned: Series = Depends(get_owned_series)):
    """Update Series-level prompt config."""
    try:
        series = pipeline.update_series(_owned.id, {"prompt_config": config})
        return signed_response(series)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================
# Series Model Settings
# ============================================================

class UpdateModelSettingsRequest(BaseModel):
    t2i_model: Optional[str] = None
    i2i_model: Optional[str] = None
    image_model: Optional[str] = None
    i2v_model: Optional[str] = None
    r2v_model: Optional[str] = None
    character_aspect_ratio: Optional[str] = None
    scene_aspect_ratio: Optional[str] = None
    prop_aspect_ratio: Optional[str] = None
    storyboard_aspect_ratio: Optional[str] = None

@app.get("/series/{series_id}/model_settings")
def get_series_model_settings(series: Series = Depends(get_owned_series)):
    """Get Series model settings."""
    return series.model_settings.model_dump()


@app.put("/series/{series_id}/model_settings")
def update_series_model_settings(settings: UpdateModelSettingsRequest, series: Series = Depends(get_owned_series)):
    """Update Series-level model settings."""
    updates = {k: v for k, v in settings.model_dump().items() if v is not None}
    if not updates:
        return signed_response(series)
    try:
        ms = series.model_settings.model_copy(update=updates)
        updated_series = pipeline.update_series(series.id, {"model_settings": ms})
        return signed_response(updated_series)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================
# Series Asset Operations
# ============================================================

@app.get("/series/{series_id}/assets")
def get_series_assets(series: Series = Depends(get_owned_series)):
    """Get all shared assets from a Series."""
    return signed_response({
        "characters": [c.model_dump() for c in series.characters],
        "scenes": [s.model_dump() for s in series.scenes],
        "props": [p.model_dump() for p in series.props],
    })


@app.post("/series/{series_id}/assets/generate")
def generate_series_asset(request: GenerateAssetRequest, background_tasks: BackgroundTasks, _owned: Series = Depends(get_owned_series)):
    """Generate a single asset for a Series (async)."""
    series_id = _owned.id
    try:
        series, task_id = pipeline.generate_series_asset(
            series_id,
            request.asset_id,
            request.asset_type,
            request.style_preset,
            request.reference_image_url,
            request.style_prompt,
            request.generation_type,
            request.prompt,
            request.apply_style,
            request.negative_prompt,
            request.batch_size,
            request.model_name
        )
        background_tasks.add_task(pipeline.process_asset_generation_task, task_id)
        response_data = series.dict()
        response_data["_task_id"] = task_id
        return signed_response(response_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/series/{series_id}/assets/toggle_lock")
def toggle_series_asset_lock(request: ToggleLockRequest, _owned: Series = Depends(get_owned_series)):
    """Toggle the locked status of a Series asset."""
    try:
        series = pipeline.toggle_series_asset_lock(_owned.id, request.asset_id, request.asset_type)
        return signed_response(series)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/series/{series_id}/assets/toggle_starred")
def toggle_series_asset_starred(request: ToggleLockRequest, _owned: Series = Depends(get_owned_series)):
    """Toggle the starred (library shortlist) status of a Series asset."""
    try:
        series = pipeline.toggle_series_asset_starred(_owned.id, request.asset_id, request.asset_type)
        return signed_response(series)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/series/{series_id}/assets/update_image")
def update_series_asset_image(request: UpdateAssetImageRequest, _owned: Series = Depends(get_owned_series)):
    """Update a Series asset's image URL."""
    try:
        series = pipeline.update_series_asset_image(_owned.id, request.asset_id, request.asset_type, request.image_url)
        return signed_response(series)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/series/{series_id}/assets/update_attributes")
def update_series_asset_attributes(request: UpdateAssetAttributesRequest, _owned: Series = Depends(get_owned_series)):
    """Update arbitrary attributes of a Series asset."""
    try:
        series = pipeline.update_series_asset_attributes(
            _owned.id, request.asset_id, request.asset_type, request.attributes
        )
        return signed_response(series)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ImportAssetsRequest(BaseModel):
    source_series_id: str
    asset_ids: List[str]


# R2V v2 Phase 5 — quick-create CRUD for series-shared assets.
# Used by Cast step's "+ 新角色 / 新场景 / 新道具" modal. Optional
# `image_url` lets the user attach a pre-uploaded master sheet so the
# new asset isn't blank.
class CreateSeriesAssetRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    persona: Optional[str] = ""        # characters only — grouping label
    image_url: Optional[str] = None    # optional uploaded master sheet
    has_grid_overlay: bool = False     # whether image_url had a proportion grid burned in
    voice_id: Optional[str] = None     # characters only — TTS voice binding


def _new_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@app.post("/series/{series_id}/characters")
def create_series_character(request: CreateSeriesAssetRequest, series: Series = Depends(get_owned_series)):
    """Create a new Character at series scope."""
    from .models import Character, AssetUnit, ImageVariant
    series_id = series.id
    char_id = _new_id("char")
    ref_sheet = AssetUnit()
    if request.image_url:
        variant = ImageVariant(id=_new_id("img"), url=request.image_url, has_grid_overlay=request.has_grid_overlay)
        ref_sheet.image_variants.append(variant)
        ref_sheet.selected_image_id = variant.id
    char = Character(
        id=char_id,
        name=request.name,
        description=request.description or "",
        persona=request.persona or "",
        voice_id=request.voice_id,
        reference_sheet=ref_sheet,
    )
    series.characters.append(char)
    series.updated_at = time.time()
    pipeline.series_store[series_id] = series
    pipeline._save_series_data()
    return signed_response(char.model_dump())


@app.post("/series/{series_id}/scenes")
def create_series_scene(request: CreateSeriesAssetRequest, series: Series = Depends(get_owned_series)):
    from .models import Scene, ImageAsset, ImageVariant
    series_id = series.id
    sid = _new_id("scene")
    image_asset = ImageAsset()
    if request.image_url:
        variant = ImageVariant(id=_new_id("img"), url=request.image_url, has_grid_overlay=request.has_grid_overlay)
        image_asset.variants.append(variant)
        image_asset.selected_id = variant.id
    scene = Scene(
        id=sid,
        name=request.name,
        description=request.description or "",
        image_url=request.image_url,
        image_asset=image_asset,
    )
    series.scenes.append(scene)
    series.updated_at = time.time()
    pipeline.series_store[series_id] = series
    pipeline._save_series_data()
    return signed_response(scene.model_dump())


@app.post("/series/{series_id}/props")
def create_series_prop(request: CreateSeriesAssetRequest, series: Series = Depends(get_owned_series)):
    from .models import Prop, ImageAsset, ImageVariant
    series_id = series.id
    pid = _new_id("prop")
    image_asset = ImageAsset()
    if request.image_url:
        variant = ImageVariant(id=_new_id("img"), url=request.image_url, has_grid_overlay=request.has_grid_overlay)
        image_asset.variants.append(variant)
        image_asset.selected_id = variant.id
    prop = Prop(
        id=pid,
        name=request.name,
        description=request.description or "",
        image_url=request.image_url,
        image_asset=image_asset,
    )
    series.props.append(prop)
    series.updated_at = time.time()
    pipeline.series_store[series_id] = series
    pipeline._save_series_data()
    return signed_response(prop.model_dump())


@app.post("/series/{series_id}/assets/import")
def import_series_assets(request: ImportAssetsRequest, _owned: Series = Depends(get_owned_series)):
    """Deep-copy assets from another Series into this one."""
    try:
        series, imported_ids, skipped_ids = pipeline.import_assets_from_series(_owned.id, request.source_series_id, request.asset_ids)
        return signed_response(series)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Global Asset Library (project-independent shared pool) — CRUD + promote
# ============================================================
# Mirrors the /series/{id}/assets endpoints, one level up: a curated,
# project-independent pool any project can reference. All mutations route
# through the ComicGenPipeline.*_library_asset methods so the Playground
# "录入资产库" flow stays consistent with these endpoints.

class CreateLibraryAssetRequest(BaseModel):
    asset_type: str                    # "character" | "scene" | "prop"
    name: str
    description: Optional[str] = ""
    persona: Optional[str] = ""        # characters only — grouping label
    image_url: Optional[str] = None    # optional pre-uploaded master image
    has_grid_overlay: bool = False     # whether image_url had a proportion grid burned in
    voice_id: Optional[str] = None     # characters only — TTS voice binding


class UpdateLibraryAssetRequest(BaseModel):
    # Generic patch — only the fields the client actually sends are applied
    # (PATCH semantics; PUT here is lenient/partial).
    name: Optional[str] = None
    description: Optional[str] = None
    persona: Optional[str] = None
    image_url: Optional[str] = None
    has_grid_overlay: Optional[bool] = None
    voice_id: Optional[str] = None
    starred: Optional[bool] = None
    locked: Optional[bool] = None
    visual_weight: Optional[int] = None


class PromoteAssetRequest(BaseModel):
    source_kind: str   # "project" | "series"
    source_id: str
    asset_type: str    # "character" | "scene" | "prop"
    asset_id: str


class ForkFromLibraryRequest(BaseModel):
    asset_type: str          # "character" | "scene" | "prop"
    library_asset_id: str    # id of the source asset in the global library


@app.get("/library/assets")
def get_library_assets(_user=Depends(auth.require_login)):
    """List all assets in the global shared pool."""
    lib = pipeline.list_library_assets()
    return signed_response({
        "characters": [c.model_dump() for c in lib.characters],
        "scenes": [s.model_dump() for s in lib.scenes],
        "props": [p.model_dump() for p in lib.props],
    })


@app.post("/library/assets")
def create_library_asset(request: CreateLibraryAssetRequest, _user=Depends(auth.require_login)):
    """Create a new asset in the global shared pool."""
    try:
        payload = request.model_dump(exclude={"asset_type"})
        asset = pipeline.create_library_asset(request.asset_type, payload)
        return signed_response(asset.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/library/assets/upload")
def upload_library_asset_image(file: UploadFile = File(...), grid_size: int = 0, grid_color: str = "black", _user=Depends(auth.require_login)):
    """Upload an image to use as a global library asset's master image.

    Saves the file under output/uploads/ (served via the /files static mount)
    and returns {"image_url": ..., "has_grid_overlay": ...}. When OSS
    is configured the returned URL is the (signed) OSS URL; otherwise a local
    relative path "uploads/<name>" resolvable through the frontend's
    getAssetUrl helper. `has_grid_overlay` echoes back whether grid_size>0 was
    applied, since this is a two-step flow — the caller then passes both
    image_url and has_grid_overlay to POST /library/assets (image_url=...) or
    PATCH /library/assets/{type}/{id} to attach it to a library asset, which
    can no longer infer grid_size on its own. Mirrors the generic /upload
    endpoint but returns the {image_url} contract the library UI expects.
    """
    try:
        data, ext = validate_image_upload(file)
        data = apply_grid_overlay(data, ext, grid_size, grid_color)
        filename = f"{uuid.uuid4()}.{ext}"
        file_path = os.path.join("output/uploads", filename)
        with open(file_path, "wb") as buffer:
            buffer.write(data)
        # Prefer OSS when configured (signed), else fall back to local path.
        oss_url = OSSImageUploader().upload_image(file_path)
        has_grid_overlay = grid_size > 0
        if oss_url:
            return signed_response({"image_url": oss_url, "has_grid_overlay": has_grid_overlay})
        return {"image_url": f"uploads/{filename}", "has_grid_overlay": has_grid_overlay}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("upload_library_asset_image failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.api_route("/library/assets/{asset_type}/{asset_id}", methods=["PUT", "PATCH"])
def update_library_asset(asset_type: str, asset_id: str, request: UpdateLibraryAssetRequest, _user=Depends(auth.require_login)):
    """Patch a global library asset (only the provided fields are applied)."""
    try:
        patch = request.model_dump(exclude_unset=True)
        asset = pipeline.update_library_asset(asset_type, asset_id, patch)
        return signed_response(asset.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/library/assets/{asset_type}/{asset_id}")
def delete_library_asset(asset_type: str, asset_id: str, force: bool = False, _user=Depends(auth.require_login)):
    """Delete an asset from the global shared pool.

    Reference-integrity (design Q2): if any storyboard frame in any project or
    series still references this asset (via scene_id / character_ids /
    prop_ids), the delete is refused with HTTP 409 and the referrers are
    listed — unless ``force=true`` is passed, which deletes anyway and leaves
    those references dangling (the asset resolver simply drops the unknown id).
    """
    try:
        pipeline.delete_library_asset(asset_type, asset_id, force=force)
        return {"status": "deleted", "asset_type": asset_type, "id": asset_id}
    except LibraryAssetInUseError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "library_asset_in_use",
                "message": str(e),
                "asset_type": e.asset_type,
                "asset_id": e.asset_id,
                "references": e.references,
                "hint": "Pass ?force=true to delete anyway.",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/library/assets/promote")
def promote_asset_to_library(request: PromoteAssetRequest, _user=Depends(auth.require_login)):
    """Deep-copy an asset from a project or series into the global pool."""
    try:
        asset = pipeline.promote_asset_to_library(
            request.source_kind, request.source_id, request.asset_type, request.asset_id
        )
        return signed_response(asset.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/assets/fork_from_library")
def fork_asset_from_library(request: ForkFromLibraryRequest, _owned: Script = Depends(get_owned_script)):
    """Fork (deep-copy) a global library asset into this project as an
    independent, editable local copy with a fresh id (design Q3, 按需 fork).

    Under live-reference (D1 活引用) semantics a project references shared
    library assets directly; this endpoint materializes a project-owned copy
    so subsequent edits no longer affect the shared original. Returns the new
    project-local asset.
    """
    try:
        asset = pipeline.fork_library_asset_to_project(
            _owned.id, request.asset_type, request.library_asset_id
        )
        return signed_response(asset.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# File Import & Episode Splitting
# ============================================================

@app.post("/series/import/preview")
async def import_file_preview(
    file: UploadFile = File(...),
    suggested_episodes: int = 3,
    user=Depends(auth.require_login),
):
    """Upload a txt/md file and get LLM episode split preview."""
    if suggested_episodes < 1 or suggested_episodes > 50:
        raise HTTPException(status_code=400, detail="建议集数应在 1-50 之间")
    try:
        content_bytes = await file.read(5 * 1024 * 1024 + 1)
        if len(content_bytes) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="文件超过 5MB 限制")
        text = content_bytes.decode("utf-8")
        if not text.strip():
            raise HTTPException(status_code=400, detail="文件内容为空")

        loop = asyncio.get_event_loop()
        episodes = await loop.run_in_executor(
            None,
            partial(pipeline.import_file_and_split, text, suggested_episodes, user.id)
        )
        # Store text in pipeline cache, return import_id instead of full text
        import_id = str(uuid.uuid4())
        pipeline._import_cache[import_id] = text
        return {
            "filename": file.filename,
            "text_length": len(text),
            "suggested_episodes": suggested_episodes,
            "episodes": episodes,
            "import_id": import_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("File import preview failed")
        raise HTTPException(status_code=500, detail=str(e))


class ConfirmImportRequest(BaseModel):
    title: str
    description: str = ""
    import_id: str = ""
    text: Optional[str] = None
    episodes: List[Dict[str, Any]]  # episode_number, title, start_marker, end_marker, ...


@app.post("/series/import/confirm")
async def import_file_confirm(request: ConfirmImportRequest, user=Depends(auth.require_login)):
    """Confirm the episode split and create Series + Episodes."""
    try:
        # Prefer import_id from cache, fallback to request.text
        text = None
        if request.import_id:
            text = pipeline._import_cache.pop(request.import_id, None)
        if not text:
            text = request.text
        if not text:
            raise ValueError("No text available. Provide import_id or text.")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(
                pipeline.create_series_from_import,
                request.title,
                text,
                request.episodes,
                request.description,
                user.id,
            )
        )
        return signed_response(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Import confirm failed")
        raise HTTPException(status_code=500, detail=str(e))


class EnvConfig(BaseModel):
    # Google Gemini — backs the LLM chain (script / storyboard / prompt polish).
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_BASE_URL: Optional[str] = None
    ALIBABA_CLOUD_ACCESS_KEY_ID: Optional[str] = None
    ALIBABA_CLOUD_ACCESS_KEY_SECRET: Optional[str] = None
    OSS_BUCKET_NAME: Optional[str] = None
    OSS_ENDPOINT: Optional[str] = None
    OSS_BASE_PATH: Optional[str] = None
    OSS_ENABLE: bool = True
    KLING_ACCESS_KEY: Optional[str] = None
    KLING_SECRET_KEY: Optional[str] = None
    VIDU_API_KEY: Optional[str] = None
    # BytePlus ModelArk / Volcano Ark — the whole Seedance family runs here.
    ARK_API_KEY: Optional[str] = None
    ARK_REGION: Optional[str] = None
    ARK_BASE_URL: Optional[str] = None
    endpoint_overrides: Dict[str, str] = Field(default_factory=dict)


def get_user_config_path() -> str:
    """
    Returns the path to the user config file.
    - Development mode: Uses .env in project root
    - Packaged app mode: Uses ~/.prismreel/config.json
    """
    from ...utils import get_user_data_dir
    
    # Check if running in packaged mode (e.g., via environment variable or frozen check)
    is_packaged = os.getenv("PRISMREEL_PACKAGED", "false").lower() == "true" or getattr(sys, 'frozen', False)
    
    if is_packaged:
        # Use user home directory for packaged app
        config_dir = get_user_data_dir()
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "config.json")
    else:
        # Use .env in project root for development
        # Get absolute path to project root (api.py is in src/apps/comic_gen/)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        return os.path.join(project_root, ".env")



def load_user_config():
    """Loads user config from file and applies to environment."""
    config_path = get_user_config_path()
    
    if config_path.endswith(".json"):
        # JSON config for packaged app
        if os.path.exists(config_path):
            try:
                import json
                with open(config_path, "r") as f:
                    config = json.load(f)
                for key, value in config.items():
                    if value:
                        os.environ[key] = value
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
    # .env is already loaded at startup via dotenv


def save_user_config(config_dict: dict):
    """Saves user config to file."""
    config_path = get_user_config_path()

    if config_path.endswith(".json"):
        # JSON config for packaged app
        import json
        existing_config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    existing_config = json.load(f)
            except:
                pass
        existing_config.update(config_dict)
        with open(config_path, "w") as f:
            json.dump(existing_config, f, indent=2)
    else:
        # .env for development
        for key, value in config_dict.items():
            if value is not None:
                set_key(config_path, key, value)


def remove_user_config_keys(keys: list):
    """Removes keys from the persisted config file."""
    if not keys:
        return
    config_path = get_user_config_path()

    if config_path.endswith(".json"):
        import json
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    existing_config = json.load(f)
                for key in keys:
                    existing_config.pop(key, None)
                with open(config_path, "w") as f:
                    json.dump(existing_config, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to remove keys from config: {e}")
    else:
        from dotenv import unset_key
        for key in keys:
            try:
                unset_key(config_path, key)
            except Exception as e:
                logger.warning(f"Failed to unset key {key} from .env: {e}")


# Load user config on startup
import sys
load_user_config()



@app.get("/config/info")
def get_config_info():
    """Returns information about the current config storage mode."""
    config_path = get_user_config_path()
    is_packaged = os.getenv("PRISMREEL_PACKAGED", "false").lower() == "true" or getattr(sys, 'frozen', False)
    return {
        "mode": "packaged" if is_packaged else "development",
        "config_path": config_path,
        "config_exists": os.path.exists(config_path)
    }


@app.post("/config/env")
def update_env_config(config: EnvConfig):
    """Updates environment configuration and saves to config file."""
    try:
        raw_config = config.dict(exclude_unset=True)

        # Extract endpoint_overrides and flatten into config_dict
        endpoint_overrides = raw_config.pop("endpoint_overrides", {})

        # Filter out None values and serialize enum values as plain strings.
        config_dict: Dict[str, str] = {}
        for key, value in raw_config.items():
            if value is None:
                continue
            if isinstance(value, bool):
                # Booleans (e.g. OSS_ENABLE) persist as "true"/"false" strings so
                # they round-trip through os.environ and the .env/config.json store.
                config_dict[key] = "true" if value else "false"
            else:
                config_dict[key] = value

        # Secret masking guard: GET /config/env returns secrets masked with the
        # bullet sentinel. If the frontend re-submits an unchanged secret it will
        # still contain bullets — skip it so we don't overwrite the real stored
        # key with the mask. Only genuinely edited (bullet-free) values persist.
        for field in list(config_dict.keys()):
            if field in SECRET_FIELDS and _MASK_CHAR in str(config_dict[field]):
                config_dict.pop(field, None)

        # Process endpoint overrides: validate keys against known providers
        from ...utils.endpoints import PROVIDER_DEFAULTS
        allowed_keys = {f"{p}_BASE_URL" for p in PROVIDER_DEFAULTS}
        keys_to_remove = []
        for env_key, value in endpoint_overrides.items():
            if env_key not in allowed_keys:
                logger.warning(f"Ignoring unknown endpoint key: {env_key}")
                continue
            if value and value.strip():
                config_dict[env_key] = value.strip()
            else:
                # Clear override: remove from env and config file
                os.environ.pop(env_key, None)
                keys_to_remove.append(env_key)

        # Update current process env
        for key, value in config_dict.items():
            os.environ[key] = value

        # Save to file
        save_user_config(config_dict)
        remove_user_config_keys(keys_to_remove)

        # Reset OSS singleton to pick up new config (non-blocking)
        try:
            OSSImageUploader.reset_instance()
            logger.info("OSS instance reset successfully")
        except Exception as oss_e:
            # OSS reset failure should not block config saving
            logger.warning(f"OSS reset failed (non-critical): {oss_e}")

        config_path = get_user_config_path()
        return {"status": "success", "message": f"Configuration saved to {config_path}"}
    except Exception as e:
        logger.exception("Failed to save environment configuration")
        raise HTTPException(status_code=500, detail=str(e))



def merged_project_payload(script) -> dict:
    """Episode payload with series-shared and global-library assets
    merged in. Each item carries a `source` field ("episode" | "series"
    | "global") so the frontend can visually distinguish where the asset
    lives and route writes appropriately (per A2 design decision —
    shared writes default to the series side; local writes stay
    episode-side; the helper `_find_asset_with_source` in pipeline
    routes mutations correctly).

    Every endpoint whose response the frontend feeds back into its
    project store must go through this — the store shallow-merges the
    response, so handing back a raw episode Script blanks the cast list
    for any episode whose assets live series-side.

    `source` is a presentation-layer concern: derived from container
    membership at read time, never persisted."""
    payload = script.model_dump()

    # Episode-local entries always carry source="episode".
    for asset_list in (payload.get("characters", []),
                      payload.get("scenes", []),
                      payload.get("props", [])):
        for item in asset_list:
            item["source"] = "episode"

    # Merge series-shared assets on top (any id not already present
    # locally — episode-local overrides series). Without this step
    # the user "loses" characters when switching between episodes of
    # the same series, because the series shared pool isn't
    # reflected on each episode's response.
    if script.series_id:
        series = pipeline.get_series(script.series_id)
        if series:
            ep_char_ids = {c.id for c in script.characters}
            ep_scene_ids = {s.id for s in script.scenes}
            ep_prop_ids = {p.id for p in script.props}
            for ch in series.characters:
                if ch.id not in ep_char_ids:
                    d = ch.model_dump()
                    d["source"] = "series"
                    payload["characters"].append(d)
            for sc in series.scenes:
                if sc.id not in ep_scene_ids:
                    d = sc.model_dump()
                    d["source"] = "series"
                    payload["scenes"].append(d)
            for pr in series.props:
                if pr.id not in ep_prop_ids:
                    d = pr.model_dump()
                    d["source"] = "series"
                    payload["props"].append(d)

    # Merge the project-independent global asset library underneath as
    # the lowest layer. Any id not already present from the episode or
    # series layers is appended with source="global" (read-time only —
    # never written back to projects.json). When the library is empty
    # this is a no-op and the response is byte-identical to before.
    lib = pipeline.library_store
    if lib.characters or lib.scenes or lib.props:
        seen_char_ids = {c["id"] for c in payload["characters"]}
        seen_scene_ids = {s["id"] for s in payload["scenes"]}
        seen_prop_ids = {p["id"] for p in payload["props"]}
        for ch in lib.characters:
            if ch.id not in seen_char_ids:
                d = ch.model_dump()
                d["source"] = "global"
                payload["characters"].append(d)
        for sc in lib.scenes:
            if sc.id not in seen_scene_ids:
                d = sc.model_dump()
                d["source"] = "global"
                payload["scenes"].append(d)
        for pr in lib.props:
            if pr.id not in seen_prop_ids:
                d = pr.model_dump()
                d["source"] = "global"
                payload["props"].append(d)
    return payload


@app.get("/projects/{script_id}")
def get_project(script: Script = Depends(get_owned_script)):
    """Retrieves a project by ID, with series-shared and global assets
    merged in (see merged_project_payload).

    Response model dropped from `Script` because of the added `source`
    field."""
    return signed_response(merged_project_payload(script))



@app.delete("/projects/{script_id}")
def delete_project(script: Script = Depends(get_owned_script)):
    """Deletes a project by ID. WARNING: This permanently removes the project from backend storage."""
    script_id = script.id
    try:
        # If project belongs to a Series, remove from episode_ids
        if script.series_id:
            series = pipeline.get_series(script.series_id)
            if series and script_id in series.episode_ids:
                series.episode_ids.remove(script_id)
                pipeline._save_series_data()

        # Remove from pipeline scripts
        del pipeline.scripts[script_id]
        pipeline._save_data()
        return {"status": "deleted", "id": script_id, "title": script.title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────
# R2V v2 Phase 4 — Cross-episode asset reconcile
# ─────────────────────────────────────────────────────────────────────
def _name_match_confidence(local_name: str, series_name: str) -> int:
    """0-100 simple confidence score.
    Phase 4 v1: exact match = 100, substring match = 75, none = 0.
    Future: embedding-based semantic similarity on `description`."""
    a, b = (local_name or "").strip().lower(), (series_name or "").strip().lower()
    if not a or not b:
        return 0
    if a == b:
        return 100
    if a in b or b in a:
        return 75
    return 0


@app.get("/projects/{script_id}/reconcile/suggestions")
def reconcile_suggestions(script: Script = Depends(get_owned_script)):
    """Compute match suggestions for the current episode's just-extracted
    entities vs the parent series's shared asset library.

    Returned shape:
    {
      "characters": [
        { local_id, local_name, suggested_series_id|null, suggested_series_name|null, confidence }
      ],
      "scenes": [...],
      "props": [...],
    }
    Frontend uses this to render the ReconcileModal after script parse.
    """
    if not script.series_id:
        # Standalone projects have no series library to reconcile against
        return {"characters": [], "scenes": [], "props": []}
    series = pipeline.get_series(script.series_id)
    if not series:
        return {"characters": [], "scenes": [], "props": []}

    def best_match(local_name: str, pool: list, key: str = "name"):
        best_id, best_name, best_conf = None, None, 0
        for item in pool:
            sname = getattr(item, key, "") if hasattr(item, key) else item.get(key, "")
            conf = _name_match_confidence(local_name, sname)
            if conf > best_conf:
                best_id, best_name, best_conf = item.id if hasattr(item, "id") else item.get("id"), sname, conf
        return best_id, best_name, best_conf

    def build(local_pool, series_pool):
        result = []
        for local in local_pool:
            sid, sname, conf = best_match(local.name, series_pool)
            result.append({
                "local_id": local.id,
                "local_name": local.name,
                "suggested_series_id": sid if conf > 0 else None,
                "suggested_series_name": sname if conf > 0 else None,
                "confidence": conf,
            })
        return result

    return {
        "characters": build(script.characters, series.characters),
        "scenes": build(script.scenes, series.scenes),
        "props": build(script.props, series.props),
    }


class ReconcileAction(BaseModel):
    local_id: str
    action: str  # "merge_into_series" | "create_new_in_series" | "skip"
    target_series_id: Optional[str] = None


class ApplyReconcileRequest(BaseModel):
    characters: List[ReconcileAction] = Field(default_factory=list)
    scenes: List[ReconcileAction] = Field(default_factory=list)
    props: List[ReconcileAction] = Field(default_factory=list)


@app.post("/projects/{script_id}/reconcile/apply")
def reconcile_apply(request: ApplyReconcileRequest, script: Script = Depends(get_owned_script)):
    """Apply user-confirmed reconcile decisions.
    - merge_into_series: drop the local episode entity, replace all
      frame references with target_series_id (the series-shared asset).
    - create_new_in_series: promote the local entity to series scope.
    - skip: no-op (keep local-only).
    """
    script_id = script.id
    if not script.series_id:
        raise HTTPException(status_code=400, detail="Project not in a series")
    series = pipeline.get_series(script.series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    def apply_list(local_pool_attr: str, series_pool_attr: str, actions: list, frame_ref_attr: Optional[str] = None):
        local_pool = getattr(script, local_pool_attr)
        series_pool = getattr(series, series_pool_attr)
        for act in actions:
            local_item = next((x for x in local_pool if x.id == act.local_id), None)
            if not local_item:
                continue
            if act.action == "create_new_in_series":
                # Promote: copy to series pool, drop from local
                series_pool.append(local_item)
                local_pool.remove(local_item)
            elif act.action == "merge_into_series" and act.target_series_id:
                # Rewire frame references then drop local
                if frame_ref_attr:
                    for frame in script.frames:
                        if frame_ref_attr == "scene_id":
                            if frame.scene_id == local_item.id:
                                frame.scene_id = act.target_series_id
                        elif frame_ref_attr == "character_ids":
                            frame.character_ids = [
                                act.target_series_id if cid == local_item.id else cid
                                for cid in frame.character_ids
                            ]
                        elif frame_ref_attr == "prop_ids":
                            frame.prop_ids = [
                                act.target_series_id if pid == local_item.id else pid
                                for pid in frame.prop_ids
                            ]
                local_pool.remove(local_item)
            # skip: do nothing
        setattr(script, local_pool_attr, local_pool)
        setattr(series, series_pool_attr, series_pool)

    apply_list("characters", "characters", request.characters, "character_ids")
    apply_list("scenes", "scenes", request.scenes, "scene_id")
    apply_list("props", "props", request.props, "prop_ids")

    script.updated_at = time.time()
    series.updated_at = time.time()
    pipeline.scripts[script_id] = script
    pipeline.series_store[series.id] = series
    pipeline._save_data()
    pipeline._save_series_data()
    return signed_response(merged_project_payload(script))


# ─────────────────────────────────────────────────────────────────────
# R2V v2 Phase 3 — "Previously on..." (上回书说到)
# ─────────────────────────────────────────────────────────────────────
def _prev_text_revision(prev_text: str) -> str:
    """Cheap revision marker for cache invalidation.
    Hash + length is sufficient — collisions don't matter, we only
    detect "did the script change since cache was built"."""
    import hashlib
    h = hashlib.md5(prev_text.encode("utf-8")).hexdigest()[:12]
    return f"{len(prev_text)}-{h}"


@app.get("/projects/{script_id}/previous_episode")
def get_previous_episode_summary(script: Script = Depends(get_owned_script)):
    """Return previous-episode raw snippet + AI summary cache state for
    the "Previously on..." right rail in the Script step.

    Response shape:
        {
          "has_previous": bool,
          "previous_episode_id": str | null,
          "previous_episode_title": str | null,
          "raw_snippet": str  (last ~600 chars of previous original_text),
          "ai_summary": str | null  (cached summary if fresh),
          "ai_summary_stale": bool  (true when prev text changed since cache),
        }
    """
    if not script.series_id:
        return {
            "has_previous": False,
            "previous_episode_id": None,
            "previous_episode_title": None,
            "raw_snippet": "",
            "ai_summary": None,
            "ai_summary_stale": False,
        }
    series = pipeline.get_series(script.series_id)
    if not series:
        return {
            "has_previous": False,
            "previous_episode_id": None,
            "previous_episode_title": None,
            "raw_snippet": "",
            "ai_summary": None,
            "ai_summary_stale": False,
        }
    # Find previous episode by ordered episode_ids — fall back to
    # episode_number ordering when episode_ids is malformed.
    try:
        idx = series.episode_ids.index(script_id)
    except ValueError:
        idx = -1
    if idx <= 0:
        # No previous episode (this IS the first or the id is missing)
        return {
            "has_previous": False,
            "previous_episode_id": None,
            "previous_episode_title": None,
            "raw_snippet": "",
            "ai_summary": None,
            "ai_summary_stale": False,
        }
    prev_id = series.episode_ids[idx - 1]
    prev = pipeline.get_script(prev_id)
    if not prev or not (prev.original_text or "").strip():
        return {
            "has_previous": False,
            "previous_episode_id": prev_id,
            "previous_episode_title": prev.title if prev else None,
            "raw_snippet": "",
            "ai_summary": None,
            "ai_summary_stale": False,
        }
    raw_snippet = (prev.original_text or "")[-800:]
    current_rev = _prev_text_revision(prev.original_text or "")
    is_stale = (
        script.last_episode_summary_cache is not None
        and script.last_episode_summary_revision != current_rev
    )
    # R2V v2 P2-a — last frames of previous episode for Storyboard
    # cross-step reference. We surface the *last 4 frames* with their
    # selected video / T2I image so authors composing this episode's
    # opening shots can see what the previous episode ended on.
    last_frames = []
    for f in (prev.frames or [])[-4:]:
        thumb_url = None
        # Prefer the selected video's poster/url, fall back to T2I image
        if getattr(f, "video_url", None):
            thumb_url = f.video_url
        elif getattr(f, "rendered_image_url", None):
            thumb_url = f.rendered_image_url
        elif getattr(f, "image_url", None):
            thumb_url = f.image_url
        elif getattr(f, "t2i_image_urls", None):
            urls = f.t2i_image_urls
            if urls:
                idx = getattr(f, "t2i_selected_index", 0) or 0
                idx = max(0, min(idx, len(urls) - 1))
                thumb_url = urls[idx]
        last_frames.append({
            "id": f.id,
            "action_description": (f.action_description or "")[:120],
            "thumbnail_url": thumb_url,
            "video_url": getattr(f, "video_url", None),
        })
    return {
        "has_previous": True,
        "previous_episode_id": prev_id,
        "previous_episode_title": prev.title,
        "raw_snippet": raw_snippet,
        "ai_summary": script.last_episode_summary_cache,
        "ai_summary_stale": is_stale,
        "last_frames": last_frames,
    }


@app.post("/projects/{script_id}/previous_episode/summary")
def generate_previous_episode_summary(script: Script = Depends(get_owned_script)):
    """On-demand AI summary of the previous episode (qwen3.6-plus).
    Per Q7-followup design: this is *user-triggered*, not auto, to
    respect LLM quota and user intent. Result is cached on the current
    episode's Script record with a revision marker for invalidation.
    """
    script_id = script.id
    if not script.series_id:
        raise HTTPException(status_code=400, detail="Episode not in a series")
    series = pipeline.get_series(script.series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    try:
        idx = series.episode_ids.index(script_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Episode not registered in series order")
    if idx <= 0:
        raise HTTPException(status_code=400, detail="No previous episode")
    prev = pipeline.get_script(series.episode_ids[idx - 1])
    if not prev or not (prev.original_text or "").strip():
        raise HTTPException(status_code=400, detail="Previous episode has no script")

    # Call LLM — keep prompt simple and bilingual-friendly
    from .llm_adapter import LLMAdapter
    prompt = (
        "请用 150-220 字概括下面这段剧本的核心情节、关键角色出场与结尾留下的悬念/钩子。"
        "不要列点，写成一段连贯的中文叙述，便于作者快速回顾上一集走到了哪里。\n\n"
        f"剧本：\n{prev.original_text}"
    )
    try:
        adapter = LLMAdapter()
        summary = adapter.chat(
            messages=[{"role": "user", "content": prompt}],
            model=None,  # use adapter default (qwen3.6-plus with fallback chain)
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")
    summary = (summary or "").strip()
    if not summary:
        raise HTTPException(status_code=502, detail="Empty summary from LLM")

    # Persist cache + revision marker on current script
    script.last_episode_summary_cache = summary
    script.last_episode_summary_revision = _prev_text_revision(prev.original_text or "")
    script.updated_at = time.time()
    pipeline.scripts[script_id] = script
    pipeline._save_data()
    return {
        "ai_summary": summary,
        "ai_summary_stale": False,
        "previous_episode_id": prev.id,
        "previous_episode_title": prev.title,
    }


@app.get("/series/{series_id}/characters/{character_id}/appearances")
def get_character_appearances(character_id: str, series: Series = Depends(get_owned_series)):
    """R2V v2 P1-c — Cross-episode character appearance summary.
    Used by Script step's @mention helper popover. Returns chronological
    list of episodes where the character appears + per-episode frame
    count + aggregated 'last seen' info."""
    char = next((c for c in series.characters if c.id == character_id), None)
    if not char:
        # Try as episode-local character — maybe id is from any episode
        for ep_id in series.episode_ids:
            ep = pipeline.get_script(ep_id)
            if ep:
                local = next((c for c in ep.characters if c.id == character_id), None)
                if local:
                    char = local
                    break
    if not char:
        raise HTTPException(status_code=404, detail="Character not found in series scope")
    appearances = []
    total_frames = 0
    for ep_id in series.episode_ids:
        ep = pipeline.get_script(ep_id)
        if not ep:
            continue
        count = sum(1 for f in ep.frames if character_id in (f.character_ids or []))
        if count > 0:
            appearances.append({
                "episode_id": ep_id,
                "episode_number": ep.episode_number,
                "episode_title": ep.title,
                "frame_count": count,
            })
            total_frames += count
    return {
        "character": {
            "id": char.id,
            "name": char.name,
            "persona": char.persona,
            "description": char.description,
        },
        "appearances": appearances,
        "total_frames": total_frames,
    }


# R2V v2 P2-b — "Next episode hook" prediction (forward-looking).
@app.get("/projects/{script_id}/next_hook")
def get_next_episode_hook(script: Script = Depends(get_owned_script)):
    """Return cached hook prediction state for the Script step's
    'Hook for next' panel. Always returns the current revision marker
    so the frontend can decide if a refresh is warranted."""
    current_text = script.original_text or ""
    current_rev = _prev_text_revision(current_text)
    is_stale = (
        script.next_hook_cache is not None
        and script.next_hook_revision != current_rev
    )
    return {
        "has_text": bool(current_text.strip()),
        "hook": script.next_hook_cache,
        "stale": is_stale,
    }


@app.post("/projects/{script_id}/next_hook")
def generate_next_episode_hook(script: Script = Depends(get_owned_script)):
    """On-demand AI prediction of the next-episode opening hook based
    on THIS episode's ending. User-triggered (no auto-generate to
    respect LLM quota)."""
    script_id = script.id
    text = script.original_text or ""
    if not text.strip():
        raise HTTPException(status_code=400, detail="Episode has no script text yet")

    from .llm_adapter import LLMAdapter
    # Use last ~1500 chars as context (the ending matters most for hooks)
    ending = text[-1500:]
    prompt = (
        "下面是一集剧本的结尾。请你站在编剧的视角，预测下一集开头可能的 hook，"
        "用 120-180 字给出 2-3 个具体方向（包括场景、角色出场、悬念点）。"
        "不要列点编号，写成连贯的中文段落，便于作者参考。\n\n"
        f"本集结尾：\n{ending}"
    )
    try:
        adapter = LLMAdapter()
        hook = adapter.chat(
            messages=[{"role": "user", "content": prompt}],
            model=None,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")
    hook = (hook or "").strip()
    if not hook:
        raise HTTPException(status_code=502, detail="Empty hook from LLM")

    script.next_hook_cache = hook
    script.next_hook_revision = _prev_text_revision(text)
    script.updated_at = time.time()
    pipeline.scripts[script_id] = script
    pipeline._save_data()
    return {"hook": hook, "stale": False}


@app.put("/projects/{script_id}/next_hook")
def update_next_episode_hook(payload: dict, script: Script = Depends(get_owned_script)):
    """Manually edit / clear the next-hook cache."""
    script_id = script.id
    hook = payload.get("hook")
    if hook is None:
        script.next_hook_cache = None
        script.next_hook_revision = None
    else:
        script.next_hook_cache = str(hook).strip()
        script.next_hook_revision = _prev_text_revision(script.original_text or "")
    script.updated_at = time.time()
    pipeline.scripts[script_id] = script
    pipeline._save_data()
    return {"hook": script.next_hook_cache, "stale": False}


@app.post("/projects/{script_id}/sync_descriptions")
def sync_descriptions(_owned: Script = Depends(get_owned_script)):
    """
    Syncs entity descriptions from Script module to Assets module.

    This endpoint forces a refresh of the project data, ensuring that any
    description changes made in the Script module are reflected in Assets.

    Note: This only syncs descriptions; generated images/videos are preserved.
    """
    try:
        updated_script = pipeline.sync_descriptions_from_script_entities(_owned.id)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AddCharacterRequest(BaseModel):
    name: str
    description: str

@app.post("/projects/{script_id}/characters")
def add_character(request: AddCharacterRequest, script: Script = Depends(get_owned_script)):
    """Adds a new character."""
    try:
        updated_script = pipeline.add_character(script.id, request.name, request.description)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/projects/{script_id}/characters/{char_id}")
def delete_character(char_id: str, script: Script = Depends(get_owned_script)):
    """Deletes a character."""
    try:
        updated_script = pipeline.delete_character(script.id, char_id)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class AddSceneRequest(BaseModel):
    name: str
    description: str

@app.post("/projects/{script_id}/scenes")
def add_scene(request: AddSceneRequest, script: Script = Depends(get_owned_script)):
    """Adds a new scene."""
    try:
        updated_script = pipeline.add_scene(script.id, request.name, request.description)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/projects/{script_id}/scenes/{scene_id}")
def delete_scene(scene_id: str, script: Script = Depends(get_owned_script)):
    """Deletes a scene."""
    try:
        updated_script = pipeline.delete_scene(script.id, scene_id)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UpdateStyleRequest(BaseModel):
    style_preset: str
    style_prompt: Optional[str] = None


@app.patch("/projects/{script_id}/style")
def update_project_style(request: UpdateStyleRequest, script: Script = Depends(get_owned_script)):
    """Updates the global style settings for a project."""
    try:
        updated_script = pipeline.update_project_style(
            script.id,
            request.style_preset,
            request.style_prompt
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/generate_assets")
def generate_assets(background_tasks: BackgroundTasks, script: Script = Depends(get_owned_script)):
    """Triggers asset generation."""
    script_id = script.id
    # Run in background to avoid blocking
    # For simplicity in this demo, we run synchronously or use background tasks
    # pipeline.generate_assets(script_id)
    # But since we want to return the updated status, we might want to run it and return.
    # Given the mock nature, it's fast.

    try:
        updated_script = pipeline.generate_assets(script_id)
        return signed_response(merged_project_payload(updated_script))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



class GenerateMotionRefRequest(BaseModel):
    """Request model for generating Motion Reference videos."""
    asset_id: str
    asset_type: str  # 'full_body' | 'head_shot' for characters; 'scene' | 'prop' for scenes and props
    prompt: Optional[str] = None
    audio_url: Optional[str] = None  # Driving audio for lip-sync
    duration: int = 5
    batch_size: int = 1


@app.post("/projects/{script_id}/assets/generate_motion_ref")
def generate_motion_ref(request: GenerateMotionRefRequest, background_tasks: BackgroundTasks, _owned: Script = Depends(get_owned_script)):
    """Generates a Motion Reference video for an asset (Character Full Body/Headshot, Scene, or Prop)."""
    script_id = _owned.id
    try:
        script, task_id = pipeline.create_motion_ref_task(
            script_id=script_id,
            asset_id=request.asset_id,
            asset_type=request.asset_type,
            prompt=request.prompt,
            audio_url=request.audio_url,
            duration=request.duration,
            batch_size=request.batch_size
        )
        
        # Add background processing
        background_tasks.add_task(pipeline.process_motion_ref_task, script_id, task_id)
        
        # Return script with task_id for frontend polling
        response_data = merged_project_payload(script)
        response_data["_task_id"] = task_id
        return signed_response(response_data)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === STORYBOARD DRAMATIZATION v2 ===

class AnalyzeToStoryboardRequest(BaseModel):
    """Request to analyze script text into storyboard frames."""
    text: str


@app.post("/projects/{script_id}/storyboard/analyze")
def analyze_to_storyboard(request: AnalyzeToStoryboardRequest, script: Script = Depends(get_owned_script)):
    """
    Analyzes script text and generates storyboard frames using AI (Prompt B).
    Replaces existing frames with newly generated ones.

    Goes through merged_project_payload for the same reason bind_voice
    does: both frontend callers feed this response straight into the
    project store, which shallow-merges it. Returning the raw episode
    Script blanked characters/scenes/props for any episode whose assets
    live in the series pool.
    """
    try:
        updated_script = pipeline.analyze_text_to_frames(script.id, request.text)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error in analyze_to_storyboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class RefinePromptRequest(BaseModel):
    """Request to refine a frame's prompt using AI."""
    frame_id: str
    raw_prompt: str
    assets: list = []  # List of asset references
    feedback: str = Field("", max_length=2000)  # User feedback for iterative refinement


@app.post("/projects/{script_id}/storyboard/refine_prompt")
def refine_storyboard_prompt(request: RefinePromptRequest, script: Script = Depends(get_owned_script)):
    """
    Refines a raw prompt into bilingual (CN/EN) prompts using AI (Prompt C).
    Returns the refined prompts and optionally updates the frame.

    SYNC handler — pipeline.refine_frame_prompt() does a blocking LLM call.
    Declared `def` (not `async def`) so FastAPI runs it on the threadpool
    and the event loop stays free for concurrent GETs.
    """
    try:
        result = pipeline.refine_frame_prompt(
            script.id,
            request.frame_id,
            request.raw_prompt,
            request.assets,
            request.feedback,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error in refine_storyboard_prompt: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/frames/{frame_id}/refine")
def refine_single_frame(frame_id: str, script: Script = Depends(get_owned_script)):
    """Phase 2: Refine a single coarse frame into a rich frame with structured fields."""
    try:
        frame = pipeline.refine_frame(script.id, frame_id)
        if not frame:
            raise HTTPException(status_code=500, detail="Refine returned no result")
        return frame.model_dump() if hasattr(frame, 'model_dump') else frame.dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error in refine_single_frame: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/storyboard/refine_batch")
def refine_storyboard_batch(script: Script = Depends(get_owned_script)):
    """Phase 2: Batch refine all coarse frames. Streams SSE events."""
    from fastapi.responses import StreamingResponse

    script_id = script.id

    def event_stream():
        for event_type, data in pipeline.refine_batch_generator(script_id):
            yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/projects/{script_id}/generate_storyboard")
def generate_storyboard(script: Script = Depends(get_owned_script)):
    """Triggers storyboard generation."""
    try:
        updated_script = pipeline.generate_storyboard(script.id)
        return signed_response(merged_project_payload(updated_script))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/projects/{script_id}/generate_video")
def generate_video(script: Script = Depends(get_owned_script)):
    """Triggers video generation."""
    try:
        updated_script = pipeline.generate_video(script.id)
        return signed_response(merged_project_payload(updated_script))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/projects/{script_id}/generate_audio")
def generate_audio(script: Script = Depends(get_owned_script)):
    """Triggers audio generation."""
    try:
        updated_script = pipeline.generate_audio(script.id)
        return signed_response(merged_project_payload(updated_script))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



class CreateVideoTaskRequest(BaseModel):
    image_url: str
    prompt: str
    frame_id: Optional[str] = None
    duration: int = 5
    seed: Optional[int] = None
    resolution: str = "720p"
    generate_audio: bool = False
    audio_url: Optional[str] = None
    prompt_extend: bool = True
    negative_prompt: Optional[str] = None
    batch_size: int = 1
    model: str = "wan2.6-i2v"
    shot_type: str = "single"  # 'single' or 'multi' (only for wan2.6-i2v)
    generation_mode: str = "i2v"  # 'i2v' (image-to-video) or 'r2v' (reference-to-video)
    reference_video_urls: List[str] = []  # Reference video URLs for R2V (max 3)
    # Kling params
    mode: Optional[str] = None
    sound: Optional[str] = None
    cfg_scale: Optional[float] = None
    # Vidu params
    vidu_audio: Optional[bool] = None
    movement_amplitude: Optional[str] = None
    # HappyHorse params
    reference_image_urls: List[str] = []  # Reference image URLs for HH R2V (max 9)
    ratio: Optional[str] = None  # Aspect ratio for HH T2V/R2V
    # Watermark toggle (wan / kling / vidu / pixverse / happyhorse video).
    # None = leave to provider default; True/False = explicit user choice.
    watermark: Optional[bool] = None
    # Source tab in the Storyboard R2V workbench. Distinct from
    # generation_mode (backend dispatcher hint) — used by the candidates
    # panel to group takes per UI tab on refresh.
    workbench_tab: Optional[str] = None  # 't2i_i2v' | 'direct_r2v'


def process_video_task(script_id: str, task_id: str):
    """Background task to generate video.

    The pipeline method has its own try/except that flips status to
    "failed" on errors during generation. This outer wrapper is a
    belt-and-suspenders writeback for exceptions that escape *before*
    that inner handler armed (e.g. `get_script` raising, persistence
    layer crashing). Without it the task would stay forever-`pending`
    and the UI would show an eternal spinner.
    """
    try:
        pipeline.process_video_task(script_id, task_id)
    except Exception as e:
        logger.exception(f"Error processing video task {task_id}")
        try:
            pipeline.mark_video_task_failed(
                script_id, task_id, f"Background error: {e}"
            )
        except Exception:
            logger.exception(
                f"Could not mark video task {task_id} as failed after wrapper exception"
            )


class AnnotateVideoTaskRequest(BaseModel):
    """User-review annotations on a video task ("抽卡 review").
    Both fields optional so the same endpoint covers star-only,
    label-only, or both. `clear_label=True` explicitly removes
    the label (None on its own means "don't change")."""
    is_starred: Optional[bool] = None
    label: Optional[str] = None
    clear_label: bool = False


@app.patch("/projects/{script_id}/video_tasks/{task_id}/annotate", response_model=VideoTask)
def annotate_video_task(task_id: str, request: AnnotateVideoTaskRequest, script: Script = Depends(get_owned_script)):
    """Set the user's star + label on a video task. Used by Storyboard's
    candidates panel for shortlist marking (multi-select) and short
    free-text notes (≤20 chars, truncated server-side)."""
    task = pipeline.annotate_video_task(
        script.id,
        task_id,
        is_starred=request.is_starred,
        label=request.label,
        clear_label=request.clear_label,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Video task not found")
    return signed_response(task)


class UpdateFrameWorkbenchRequest(BaseModel):
    """Storyboard R2V workbench state writeback. Every field optional;
    only what the caller passes gets updated. The server clamps lists
    and indices to safe ranges; rejects unknown enum values."""
    workbench_tab_mode: Optional[str] = None  # 't2i_i2v' | 'direct_r2v'
    t2i_image_urls: Optional[List[str]] = None  # full ordered history, server caps at 10 FIFO
    t2i_selected_index: Optional[int] = None  # active首帧 index, clamped to range
    workbench_generate_count: Optional[int] = None  # batch size, clamped to [1, 6]


@app.patch("/projects/{script_id}/frames/{frame_id}/workbench", response_model=StoryboardFrame)
def update_frame_workbench(
    frame_id: str, request: UpdateFrameWorkbenchRequest, script: Script = Depends(get_owned_script)
):
    """Persist Storyboard R2V workbench state onto a frame so it
    survives refresh and cross-device opens. Previously this state
    lived only in React component state and got lost on reload."""
    try:
        frame = pipeline.update_frame_workbench(
            script.id,
            frame_id,
            workbench_tab_mode=request.workbench_tab_mode,
            t2i_image_urls=request.t2i_image_urls,
            t2i_selected_index=request.t2i_selected_index,
            workbench_generate_count=request.workbench_generate_count,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if frame is None:
        raise HTTPException(status_code=404, detail="Script or frame not found")
    return signed_response(frame)


@app.post("/projects/{script_id}/video_tasks/{task_id}/cancel", response_model=VideoTask)
def cancel_video_task(task_id: str, script: Script = Depends(get_owned_script)):
    """Mark a video task as failed-by-cancel. We can't actually yank a
    running provider call mid-flight (the provider keeps rendering on
    its side), but flipping the local status to "failed" unblocks the
    UI and puts the user back in control. Treats already-completed
    tasks as a no-op."""
    ok = pipeline.mark_video_task_failed(script.id, task_id, "Canceled by user")
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Video task not found or already completed",
        )
    updated_script = pipeline.get_script(script.id)
    task = next(
        (t for t in (updated_script.video_tasks if updated_script else []) if t.id == task_id),
        None,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Video task not found")
    return signed_response(task)


@app.post("/projects/{script_id}/video_tasks", response_model=List[VideoTask])
def create_video_task(request: CreateVideoTaskRequest, background_tasks: BackgroundTasks, _owned: Script = Depends(get_owned_script)):
    """Creates new video generation tasks."""
    script_id = _owned.id
    try:
        tasks = []
        for _ in range(request.batch_size):
            script, task_id = pipeline.create_video_task(
                script_id=script_id,
                image_url=request.image_url,
                prompt=request.prompt,
                frame_id=request.frame_id,
                duration=request.duration,
                seed=request.seed,
                resolution=request.resolution,
                generate_audio=request.generate_audio,
                audio_url=request.audio_url,
                prompt_extend=request.prompt_extend,
                negative_prompt=request.negative_prompt,
                model=request.model,
                shot_type=request.shot_type,
                generation_mode=request.generation_mode,
                reference_video_urls=request.reference_video_urls,
                reference_image_urls=request.reference_image_urls,
                ratio=request.ratio,
                watermark=request.watermark,
                mode=request.mode,
                sound=request.sound,
                cfg_scale=request.cfg_scale,
                vidu_audio=request.vidu_audio,
                movement_amplitude=request.movement_amplitude,
                workbench_tab=request.workbench_tab,
            )

            # Find the created task object
            created_task = next((t for t in script.video_tasks if t.id == task_id), None)
            if created_task:
                tasks.append(created_task)

            # Add background processing
            background_tasks.add_task(pipeline.process_video_task, script_id, task_id)

        return signed_response(tasks)

    except ValueError as e:
        # Validation failures from pipeline.create_video_task (model⇄
        # mode⇄refs mismatch, missing references for R2V, etc.) are
        # the user's responsibility to fix — surface as 400 so the
        # frontend can show an inline error instead of treating it
        # as a server error.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("An error occurred")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/assets/generate")
def generate_single_asset(request: GenerateAssetRequest, background_tasks: BackgroundTasks, _owned: Script = Depends(get_owned_script)):
    """Generates a single asset with specific options (async).
    Returns immediately with task_id for polling progress."""
    try:
        script, task_id = pipeline.create_asset_generation_task(
            _owned.id,
            request.asset_id,
            request.asset_type,
            request.style_preset,
            request.reference_image_url,
            request.style_prompt,
            request.generation_type,
            request.prompt,
            request.apply_style,
            request.negative_prompt,
            request.batch_size,
            request.model_name,
            request.aspect_ratio,
        )
        
        # Add background processing
        background_tasks.add_task(pipeline.process_asset_generation_task, task_id)
        
        # Return script with task_id for frontend polling
        response_data = merged_project_payload(script)
        response_data["_task_id"] = task_id
        return signed_response(response_data)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    """Returns the status of an asset generation task for polling."""
    status = pipeline.get_asset_generation_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # If completed, return the updated script as well
    if status["status"] == "completed":
        script = pipeline.get_script(status["script_id"])
        if script:
            status["script"] = signed_response(script).body.decode('utf-8')
    
    return status


class GenerateAssetVideoRequest(BaseModel):
    prompt: Optional[str] = None
    duration: int = 5
    aspect_ratio: Optional[str] = None


@app.post("/projects/{script_id}/assets/{asset_type}/{asset_id}/generate_video")
def generate_asset_video(asset_type: str, asset_id: str, request: GenerateAssetVideoRequest, background_tasks: BackgroundTasks, _owned: Script = Depends(get_owned_script)):
    """Generates a video for a specific asset (I2V)."""
    script_id = _owned.id
    try:
        script, task_id = pipeline.create_asset_video_task(
            script_id,
            asset_id,
            asset_type,
            request.prompt,
            request.duration,
            request.aspect_ratio
        )
        
        # Add background processing
        background_tasks.add_task(pipeline.process_video_task, script_id, task_id)
        
        return signed_response(merged_project_payload(script))

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/projects/{script_id}/assets/{asset_type}/{asset_id}/videos/{video_id}")
def delete_asset_video(asset_type: str, asset_id: str, video_id: str, script: Script = Depends(get_owned_script)):
    """Deletes a video from an asset."""
    try:
        updated_script = pipeline.delete_asset_video(
            script.id,
            asset_id,
            asset_type,
            video_id
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/projects/{script_id}/assets/toggle_lock")
def toggle_asset_lock(request: ToggleLockRequest, script: Script = Depends(get_owned_script)):
    """Toggles the locked status of an asset."""
    try:
        updated_script = pipeline.toggle_asset_lock(
            script.id,
            request.asset_id,
            request.asset_type
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/assets/toggle_starred")
def toggle_asset_starred(request: ToggleLockRequest, script: Script = Depends(get_owned_script)):
    """Toggles the starred (library shortlist) status of an asset."""
    try:
        updated_script = pipeline.toggle_asset_starred(
            script.id,
            request.asset_id,
            request.asset_type
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/projects/{script_id}/assets/update_image")
def update_asset_image(request: UpdateAssetImageRequest, script: Script = Depends(get_owned_script)):
    """Updates an asset's image URL manually."""
    try:
        updated_script = pipeline.update_asset_image(
            script.id,
            request.asset_id,
            request.asset_type,
            request.image_url
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/projects/{script_id}/assets/update_attributes")
def update_asset_attributes(request: UpdateAssetAttributesRequest, script: Script = Depends(get_owned_script)):
    """Updates arbitrary attributes of an asset."""
    try:
        updated_script = pipeline.update_asset_attributes(
            script.id,
            request.asset_id,
            request.asset_type,
            request.attributes
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



class UpdateAssetDescriptionRequest(BaseModel):
    asset_id: str
    asset_type: str
    description: str


@app.post("/projects/{script_id}/assets/update_description")
def update_asset_description(request: UpdateAssetDescriptionRequest, script: Script = Depends(get_owned_script)):
    """Updates an asset's description."""
    try:
        updated_script = pipeline.update_asset_description(
            script.id,
            request.asset_id,
            request.asset_type,
            request.description
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



class SelectVariantRequest(BaseModel):
    asset_id: str
    asset_type: str
    variant_id: str
    generation_type: str = None  # For character: "full_body", "three_view", "headshot"

@app.post("/projects/{script_id}/assets/variant/select")
def select_asset_variant(request: SelectVariantRequest, script: Script = Depends(get_owned_script)):
    """Selects a specific variant for an asset."""
    try:
        updated_script = pipeline.select_asset_variant(
            script.id,
            request.asset_id,
            request.asset_type,
            request.variant_id,
            request.generation_type
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class DeleteVariantRequest(BaseModel):
    asset_id: str
    asset_type: str
    variant_id: str

@app.post("/projects/{script_id}/assets/variant/delete")
def delete_asset_variant(request: DeleteVariantRequest, script: Script = Depends(get_owned_script)):
    """Deletes a specific variant from an asset."""
    try:
        updated_script = pipeline.delete_asset_variant(
            script.id,
            request.asset_id,
            request.asset_type,
            request.variant_id
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class FavoriteVariantRequest(BaseModel):
    asset_id: str
    asset_type: str
    variant_id: str
    generation_type: Optional[str] = None  # For character: 'full_body', 'three_view', 'headshot'
    is_favorited: bool

@app.post("/projects/{script_id}/assets/variant/favorite")
def toggle_variant_favorite(request: FavoriteVariantRequest, script: Script = Depends(get_owned_script)):
    """Toggles the favorite status of a variant. Favorited variants won't be auto-deleted when limit is reached."""
    try:
        updated_script = pipeline.toggle_variant_favorite(
            script.id,
            request.asset_id,
            request.asset_type,
            request.variant_id,
            request.is_favorited,
            request.generation_type
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/projects/{script_id}/model_settings")
def update_model_settings(request: UpdateModelSettingsRequest, script: Script = Depends(get_owned_script)):
    """Updates project's model settings for T2I/I2I/I2V and aspect ratios."""
    try:
        updated_script = pipeline.update_model_settings(
            script.id,
            request.t2i_model,
            request.i2i_model,
            request.i2v_model,
            r2v_model=request.r2v_model,
            character_aspect_ratio=request.character_aspect_ratio,
            scene_aspect_ratio=request.scene_aspect_ratio,
            prop_aspect_ratio=request.prop_aspect_ratio,
            storyboard_aspect_ratio=request.storyboard_aspect_ratio,
            image_model=request.image_model,
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdatePromptConfigRequest(BaseModel):
    storyboard_polish: str = ""
    video_polish: str = ""
    r2v_polish: str = ""
    entity_extraction: str = ""
    style_analysis: str = ""
    storyboard_extraction: str = ""


@app.get("/projects/{script_id}/prompt_config")
def get_prompt_config(script: Script = Depends(get_owned_script)):
    """Returns project prompt_config and system default prompts for reference."""
    try:
        config = script.prompt_config if hasattr(script, 'prompt_config') else PromptConfig()
        return {
            "prompt_config": config.model_dump(),
            "defaults": {
                "storyboard_polish": DEFAULT_STORYBOARD_POLISH_PROMPT,
                "video_polish": DEFAULT_VIDEO_POLISH_PROMPT,
                "r2v_polish": DEFAULT_R2V_POLISH_PROMPT,
                "storyboard_extraction": DEFAULT_STORYBOARD_EXTRACTION_PROMPT,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/projects/{script_id}/prompt_config")
def update_prompt_config(request: UpdatePromptConfigRequest, script: Script = Depends(get_owned_script)):
    """Updates project custom prompt configuration. Empty string = use system default."""
    try:
        existing = getattr(script, "prompt_config", None)
        preserved_polish_model = getattr(existing, "polish_model", "") if existing else ""
        script.prompt_config = PromptConfig(
            storyboard_polish=request.storyboard_polish,
            video_polish=request.video_polish,
            r2v_polish=request.r2v_polish,
            entity_extraction=request.entity_extraction,
            style_analysis=request.style_analysis,
            storyboard_extraction=request.storyboard_extraction,
            polish_model=preserved_polish_model,
        )
        pipeline._save_data()
        return {"prompt_config": script.prompt_config.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/prompt_defaults")
def get_prompt_defaults():
    """Return the built-in default system prompts for all configurable prompt keys.

    The frontend uses this to pre-fill the prompt fields and to compute the
    "delta" on save (a field equal to its default is stored as "" so the
    built-in default is used instead of pinning a snapshot).
    """
    return {
        "storyboard_polish": DEFAULT_STORYBOARD_POLISH_PROMPT,
        "video_polish": DEFAULT_VIDEO_POLISH_PROMPT,
        "r2v_polish": DEFAULT_R2V_POLISH_PROMPT,
        "entity_extraction": DEFAULT_ENTITY_EXTRACTION_PROMPT,
        "style_analysis": DEFAULT_STYLE_ANALYSIS_PROMPT,
        "storyboard_extraction": DEFAULT_STORYBOARD_EXTRACTION_PROMPT,
    }


class BindVoiceRequest(BaseModel):
    voice_id: str
    voice_name: str


@app.post("/projects/{script_id}/characters/{char_id}/voice")
def bind_voice(char_id: str, request: BindVoiceRequest, script: Script = Depends(get_owned_script)):
    """Binds a voice to a character.

    Works on series-shared characters too, so the response goes through
    merged_project_payload — the frontend merges it straight into its
    project store and would otherwise lose the shared cast. Response
    model dropped from `Script` for the same `source` field reason as
    GET /projects/{id}."""
    try:
        updated_script = pipeline.bind_voice(script.id, char_id, request.voice_id, request.voice_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return signed_response(merged_project_payload(updated_script))


class UpdateVoiceParamsRequest(BaseModel):
    speed: float = 1.0
    pitch: float = 1.0
    volume: int = 50


@app.put("/projects/{script_id}/characters/{char_id}/voice_params")
def update_voice_params(char_id: str, request: UpdateVoiceParamsRequest, script: Script = Depends(get_owned_script)):
    """Updates voice parameters for a character."""
    char = next((c for c in script.characters if c.id == char_id), None)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    char.voice_speed = request.speed
    char.voice_pitch = request.pitch
    char.voice_volume = request.volume
    pipeline._save_data()
    return signed_response(merged_project_payload(script))


@app.get("/voices")
def get_voices():
    """Returns list of available voices."""
    return pipeline.audio_generator.get_available_voices()


class VoicePreviewRequest(BaseModel):
    """PR-3g #3 · request shape for /voice/preview endpoint.

    Backs the Voice picker modal's inline ▶ button. Frontend hits this
    when user previews a voice card; backend either returns a cached
    URL or generates fresh audio via TTSProcessor.
    """
    voice_id: str
    text: str
    speed: float = 1.0
    pitch: float = 1.0
    volume: int = 50
    instructions: Optional[str] = None


@app.post("/voice/preview")
def voice_preview(request: VoicePreviewRequest):
    """Generate or fetch cached preview audio for a voice.

    Cache key = md5(voice_id|text|speed|pitch|volume|instructions). First
    call triggers TTSProcessor.synthesize() and writes to
    output/cache/voice_preview/{key}.mp3. Subsequent identical calls
    return the cached URL instantly.

    Legacy CosyVoice voice_ids are migrated to a Gemini voice inside the TTS
    layer (config/voice_migration.yaml), so no per-voice model override is
    needed any more — every voice runs on the same Gemini TTS model.

    Spec: r2v-workflow-v3-unified.md §4.2.3 (cache strategy) + Q5 b/c.
    """
    import hashlib
    if not pipeline.audio_generator.tts:
        raise HTTPException(
            status_code=503,
            detail="TTS service unavailable. Check GEMINI_API_KEY configuration.",
        )

    model_override = None
    family_override = None

    cache_dir = "output/cache/voice_preview"
    os.makedirs(cache_dir, exist_ok=True)
    cache_key = hashlib.md5(
        f"{request.voice_id}|{request.text}|{request.speed}|{request.pitch}|{request.volume}|{request.instructions or ''}".encode("utf-8")
    ).hexdigest()
    cache_path = os.path.join(cache_dir, f"{cache_key}.mp3")
    cached = os.path.exists(cache_path)

    if not cached:
        try:
            pipeline.audio_generator.tts.synthesize(
                text=request.text,
                output_path=cache_path,
                voice=request.voice_id,
                speech_rate=request.speed,
                pitch_rate=request.pitch,
                volume=request.volume,
                instructions=request.instructions,
                model_override=model_override,
                family_override=family_override,
            )
        except Exception as e:
            logger.error(f"[/voice/preview] TTS error voice={request.voice_id}: {e}")
            raise HTTPException(status_code=500, detail=f"TTS generation failed: {e}")

    # Static mount /files maps to output/, so the relative path under output/
    # becomes the URL path frontend can hit. signed_response wraps for OSS
    # signing when configured, no-op otherwise.
    url = f"cache/voice_preview/{cache_key}.mp3"
    return signed_response({"url": url, "cached": cached})


class GenerateLineAudioRequest(BaseModel):
    speed: float = 1.0
    pitch: float = 1.0
    volume: int = 50
    instructions: Optional[str] = None  # PR-3j · chip emotion + free text


@app.post("/projects/{script_id}/frames/{frame_id}/audio")
def generate_line_audio(frame_id: str, request: GenerateLineAudioRequest, script: Script = Depends(get_owned_script)):
    """Generates audio for a specific frame with parameters."""
    try:
        updated_script = pipeline.generate_dialogue_line(
            script.id, frame_id,
            request.speed, request.pitch, request.volume,
            instructions=request.instructions,
        )
        return signed_response(merged_project_payload(updated_script))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────
# PR-3k · Audio mix endpoints (BGM presets + per-script mix settings)
# Backs the Assembly Mix phase.
# ─────────────────────────────────────────────────────────────

@app.get("/bgm/presets")
def list_bgm_presets():
    """Return the BGM preset catalog. UI populates the Mix phase picker."""
    from .audio import get_bgm_presets
    return get_bgm_presets()


# ─────────────────────────────────────────────────────────────
# V-1 · Subtitle endpoints (templates + preview + settings + export)
# ─────────────────────────────────────────────────────────────


class UpdateSubtitleSettingsRequest(BaseModel):
    enabled: bool = True
    template_id: str = "douyin"
    style_override: Optional[Dict[str, Any]] = None


@app.get("/subtitle/templates")
def list_subtitle_templates():
    """Available burned-in subtitle style templates."""
    from .subtitle import SUBTITLE_TEMPLATES

    return [{"id": tid, **style.model_dump()} for tid, style in SUBTITLE_TEMPLATES.items()]


@app.get("/projects/{script_id}/subtitle/preview")
def preview_subtitles(script: Script = Depends(get_owned_script)):
    """Cue list derived from dialogue + TTS timing. No rendering, no ASR."""
    try:
        return pipeline.get_subtitle_preview(script.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/projects/{script_id}/subtitle/settings")
def update_subtitle_settings(request: UpdateSubtitleSettingsRequest, script: Script = Depends(get_owned_script)):
    from .models import SubtitleSettings, SubtitleStyle
    from .subtitle import SUBTITLE_TEMPLATES

    if request.template_id not in SUBTITLE_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template '{request.template_id}'. "
            f"Available: {sorted(SUBTITLE_TEMPLATES)}",
        )

    # Build the settings OUTSIDE the not-found handler below. pydantic's
    # ValidationError subclasses ValueError, so constructing inside that
    # `except ValueError -> 404` would report a bad style_override on a
    # perfectly existing project as "project not found" — sending the UI to
    # a missing-project state instead of showing a field error.
    try:
        settings = SubtitleSettings(
            enabled=request.enabled,
            template_id=request.template_id,
            style_override=(
                SubtitleStyle(**request.style_override) if request.style_override else None
            ),
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid subtitle style: {e}")

    try:
        updated_script = pipeline.update_subtitle_settings(script.id, settings)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/projects/{script_id}/subtitle/export")
def export_subtitle(fmt: str = "ass", script: Script = Depends(get_owned_script)):
    from fastapi.responses import FileResponse

    if fmt not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="fmt must be 'ass' or 'srt'")
    try:
        path = pipeline.export_subtitle_file(script.id, fmt)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(path, filename=os.path.basename(path))


class AudioMixRequest(BaseModel):
    bgm_url: Optional[str] = None  # null clears bgm
    dialogue_volume: Optional[int] = None  # 0-100
    bgm_volume: Optional[int] = None
    sfx_volume: Optional[int] = None


@app.put("/projects/{script_id}/audio_mix")
def update_audio_mix(request: AudioMixRequest, script: Script = Depends(get_owned_script)):
    """Set BGM + per-track mix levels for the final merge.

    PATCH-style: only fields explicitly present in the request body are
    applied. Using `model_fields_set` (Pydantic v2) lets us distinguish
    "omitted" from "explicit null" — clients pass `bgm_url: null` to clear
    the BGM, which the old `is not None` check silently swallowed.
    """
    fields_set = request.model_fields_set
    if "bgm_url" in fields_set:
        script.bgm_url = request.bgm_url or None  # null and "" both clear
    mix = dict(script.mix_settings or {"dialogue": 100, "bgm": 35, "sfx": 60})
    if "dialogue_volume" in fields_set and request.dialogue_volume is not None:
        mix["dialogue"] = max(0, min(100, request.dialogue_volume))
    if "bgm_volume" in fields_set and request.bgm_volume is not None:
        mix["bgm"] = max(0, min(100, request.bgm_volume))
    if "sfx_volume" in fields_set and request.sfx_volume is not None:
        mix["sfx"] = max(0, min(100, request.sfx_volume))
    script.mix_settings = mix
    pipeline._save_data()
    return signed_response(merged_project_payload(script))


# ─────────────────────────────────────────────────────────────
# 卡点 · Beat-synced shot trimming
# ─────────────────────────────────────────────────────────────


@app.get("/projects/{script_id}/beats")
def analyze_project_beats(script: Script = Depends(get_owned_script)):
    """Detect tempo and the beat grid of this project's BGM.

    The BPM is a suggestion, not a verdict — tempo estimation hits an octave
    ambiguity often enough (a 128 BPM click track reads as 63.8) that the UI
    lets the user correct it. See beats.estimate_bpm.
    """
    from ...utils.safe_path import safe_resolve_path

    from .beats import BeatAnalysisError, analyze

    if not script.bgm_url:
        raise HTTPException(
            status_code=400,
            detail="该项目还没有设置 BGM，请先在音频混音里选择或上传背景音乐",
        )

    try:
        path = safe_resolve_path("output", script.bgm_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"BGM 路径无效: {e}")

    try:
        result = analyze(path)
    except BeatAnalysisError as e:
        # A tone or a silent track is a real, explainable outcome — surface the
        # reason rather than a 500 the user cannot act on.
        raise HTTPException(status_code=422, detail=str(e))

    result["shots"] = _shot_trim_table(script)
    return result


def _shot_trim_table(script) -> List[Dict[str, Any]]:
    """Per-shot source length + current trim, for the beat-sync panel.

    Reuses collect_render_segments so the panel lists exactly the shots the
    render will emit — a frame whose take is missing is absent from both.
    Source durations live only on disk, so the UI cannot compute beat counts
    or clamp a "+1 beat" without this.
    """
    from ...utils.safe_path import safe_resolve_path

    from .editing import collect_render_segments

    segments = collect_render_segments(
        script, resolve=lambda u: safe_resolve_path("output", u)
    )
    return [
        {
            "frame_id": seg.frame_id,
            "source_duration_s": round(seg.source_duration_s or 0.0, 3),
            "trim_end_s": round(seg.duration_s, 3) if seg.source_duration_s
            and seg.duration_s < seg.source_duration_s - 1e-6 else None,
        }
        for seg in segments
    ]


class AlignBeatsRequest(BaseModel):
    bpm: float
    min_beats: int = 1


@app.post("/projects/{script_id}/beats/align")
def align_shots_to_beats(request: AlignBeatsRequest, script: Script = Depends(get_owned_script)):
    """Snap every shot's length to a whole number of beats at the given BPM.

    The BPM comes from the client rather than being re-detected, because the
    user is allowed to correct the detected value — octave errors are common
    enough that aligning to a number they already rejected would be worse than
    useless.
    """
    from ...utils.safe_path import safe_resolve_path

    from .beats import snap_to_beats
    from .editing import collect_render_segments

    if request.bpm <= 0:
        raise HTTPException(status_code=400, detail=f"BPM 必须为正数，收到 {request.bpm}")

    interval = 60.0 / request.bpm
    segments = collect_render_segments(
        script, resolve=lambda u: safe_resolve_path("output", u)
    )
    by_id = {f.id: f for f in script.frames}

    for seg in segments:
        source = seg.source_duration_s or 0.0
        if source <= 0:
            continue
        target = snap_to_beats(source, interval, min_beats=max(1, request.min_beats))
        frame = by_id.get(seg.frame_id)
        if frame is None:
            continue
        # An unchanged length is stored as None so the render skips the out
        # point entirely rather than round-tripping a no-op trim.
        frame.trim_end_s = None if abs(target - source) < 1e-6 else round(target, 4)

    pipeline._save_data()
    return signed_response(merged_project_payload(script))


class UpdateFrameTrimsRequest(BaseModel):
    # frame_id -> seconds, or null to clear that frame's trim
    trims: Dict[str, Optional[float]]


@app.put("/projects/{script_id}/frames/trims")
def update_frame_trims(request: UpdateFrameTrimsRequest, script: Script = Depends(get_owned_script)):
    """Set per-shot trimmed durations for beat sync.

    Batched on purpose: "align everything to the beat" writes every frame at
    once, and one request per shot would leave the project half-aligned if any
    of them failed.
    """
    by_id = {f.id: f for f in script.frames}
    unknown = [fid for fid in request.trims if fid not in by_id]
    if unknown:
        raise HTTPException(status_code=404, detail=f"未知的分镜 id: {unknown}")

    for fid, seconds in request.trims.items():
        if seconds is not None and seconds <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"分镜 {fid} 的裁剪时长必须为正数，收到 {seconds}",
            )
        by_id[fid].trim_end_s = seconds

    pipeline._save_data()
    return signed_response(merged_project_payload(script))


class DubPreviewRequest(BaseModel):
    video_task_id: str
    offset_ms: int = 0


@app.post("/projects/{script_id}/frames/{frame_id}/dub/preview")
def preview_dub(frame_id: str, request: DubPreviewRequest, script: Script = Depends(get_owned_script)):
    """Generate a preview dub (cached Demucs + fast adelay+amix+mux)."""
    try:
        updated_script = pipeline.preview_dub(
            script.id, frame_id,
            video_task_id=request.video_task_id,
            offset_ms=request.offset_ms,
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/frames/{frame_id}/dub/apply")
def apply_dub(frame_id: str, script: Script = Depends(get_owned_script)):
    """Promote current preview to official dubbed video."""
    try:
        updated_script = pipeline.apply_dub(script.id, frame_id)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/projects/{script_id}/frames/{frame_id}/dub")
def revert_frame_dub(frame_id: str, script: Script = Depends(get_owned_script)):
    """Revert dubbing — remove dubbed+preview, keep bg cache."""
    try:
        updated_script = pipeline.revert_dub(script.id, frame_id)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/projects/{script_id}/dialogue_audio/batch")
def generate_dialogue_audio_batch(script: Script = Depends(get_owned_script)):
    """PR-3j · Generate audio for every frame that has dialogue.

    Idempotent re-use: frames whose audio is already up-to-date (matching
    text/voice/instructions hash) are skipped. Stale + missing frames get
    regenerated using each character's bound voice.

    Returns the updated script plus _batch_stats with generated/skipped/failed counts.
    """
    from .audio import dialogue_audio_is_stale
    script_id = script.id
    try:
        generated = 0
        skipped = 0
        failed = 0
        no_voice = 0
        for frame in script.frames:
            dialogue_text = (
                (frame.dialogue_structured.line if hasattr(frame, 'dialogue_structured') and frame.dialogue_structured else None)
                or frame.dialogue
            )
            if not dialogue_text:
                continue
            # Shares one resolver with the single-frame path so both agree on
            # where a character may live (episode / series / global library).
            speaker = pipeline.resolve_dialogue_speaker(script, frame)
            if not speaker or not speaker.voice_id:
                no_voice += 1
                continue
            if frame.audio_url and not dialogue_audio_is_stale(frame, speaker):
                skipped += 1
                continue
            try:
                pipeline.generate_dialogue_line(script_id, frame.id)
            except Exception as exc:
                logger.error(f"[batch_dialogue_audio] frame={frame.id} error={exc}")
                failed += 1
                continue
            # A TTS failure does not raise — generate_dialogue records it on
            # the frame so the single-frame endpoint can answer 200 and let
            # the UI show the error inline. "No exception" is therefore not
            # proof of success; the frame's own outcome is.
            if frame.audio_error or not frame.audio_url:
                logger.error(
                    f"[batch_dialogue_audio] frame={frame.id} "
                    f"audio_error={frame.audio_error!r}"
                )
                failed += 1
            else:
                generated += 1
        logger.info(f"[batch_dialogue_audio] script={script_id} generated={generated} skipped={skipped} failed={failed} no_voice={no_voice}")
        script = pipeline.get_script(script_id)
        response_data = merged_project_payload(script)
        response_data["_batch_stats"] = {"generated": generated, "skipped": skipped, "failed": failed, "no_voice": no_voice}
        return signed_response(response_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/mix/generate_sfx")
def generate_mix_sfx(script: Script = Depends(get_owned_script)):
    """Triggers Video-to-Audio SFX generation for all frames."""
    # Re-using generate_audio for now as it covers everything,
    # but ideally we'd have granular methods in pipeline.
    # Let's just call generate_audio again, it's idempotent-ish.
    try:
        updated_script = pipeline.generate_audio(script.id)
        return signed_response(merged_project_payload(updated_script))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/mix/generate_bgm")
def generate_mix_bgm(script: Script = Depends(get_owned_script)):
    """Triggers BGM generation."""
    try:
        updated_script = pipeline.generate_audio(script.id)
        return signed_response(merged_project_payload(updated_script))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ToggleFrameLockRequest(BaseModel):
    frame_id: str


@app.post("/projects/{script_id}/frames/toggle_lock")
def toggle_frame_lock(request: ToggleFrameLockRequest, script: Script = Depends(get_owned_script)):
    """Toggles the locked status of a frame."""
    try:
        updated_script = pipeline.toggle_frame_lock(
            script.id,
            request.frame_id
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateFrameRequest(BaseModel):
    frame_id: str
    image_prompt: Optional[str] = None
    action_description: Optional[str] = None
    # The storyboard reads a shot's prompt from visual_description when the
    # frame has been refined, so edits to such a frame have to be writable
    # here — otherwise they land in action_description and stay shadowed.
    visual_description: Optional[str] = None
    dialogue: Optional[str] = None
    camera_angle: Optional[str] = None
    scene_id: Optional[str] = None
    character_ids: Optional[List[str]] = None
    duration: Optional[int] = None
    shot_size: Optional[str] = None
    camera_movement_description: Optional[str] = None
    transition_hint: Optional[str] = None

@app.post("/projects/{script_id}/frames/update")
def update_frame(request: UpdateFrameRequest, script: Script = Depends(get_owned_script)):
    """Updates frame data (prompt, scene, characters, etc.)."""
    try:
        updated_script = pipeline.update_frame(
            script.id,
            request.frame_id,
            image_prompt=request.image_prompt,
            action_description=request.action_description,
            visual_description=request.visual_description,
            dialogue=request.dialogue,
            camera_angle=request.camera_angle,
            scene_id=request.scene_id,
            character_ids=request.character_ids,
            duration=request.duration,
            shot_size=request.shot_size,
            camera_movement_description=request.camera_movement_description,
            transition_hint=request.transition_hint,
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class AddFrameRequest(BaseModel):
    scene_id: Optional[str] = None
    action_description: str = ""
    camera_angle: str = "medium_shot"
    insert_at: Optional[int] = None

@app.post("/projects/{script_id}/frames")
def add_frame(request: AddFrameRequest, script: Script = Depends(get_owned_script)):
    """Adds a new storyboard frame."""
    try:
        updated_script = pipeline.add_frame(
            script.id,
            request.scene_id,
            request.action_description,
            request.camera_angle,
            request.insert_at
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/projects/{script_id}/frames/{frame_id}")
def delete_frame(frame_id: str, script: Script = Depends(get_owned_script)):
    """Deletes a storyboard frame."""
    try:
        updated_script = pipeline.delete_frame(script.id, frame_id)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CopyFrameRequest(BaseModel):
    frame_id: str
    insert_at: Optional[int] = None

@app.post("/projects/{script_id}/frames/copy")
def copy_frame(request: CopyFrameRequest, script: Script = Depends(get_owned_script)):
    """Copies a storyboard frame."""
    try:
        updated_script = pipeline.copy_frame(script.id, request.frame_id, request.insert_at)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ReorderFramesRequest(BaseModel):
    frame_ids: List[str]

@app.put("/projects/{script_id}/frames/reorder")
def reorder_frames(request: ReorderFramesRequest, script: Script = Depends(get_owned_script)):
    """Reorders storyboard frames."""
    try:
        updated_script = pipeline.reorder_frames(script.id, request.frame_ids)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class RenderFrameRequest(BaseModel):
    frame_id: str
    composition_data: Optional[Dict[str, Any]] = None
    prompt: str
    batch_size: int = 1


@app.post("/projects/{script_id}/storyboard/render")
def render_frame(request: RenderFrameRequest, script: Script = Depends(get_owned_script)):
    """Renders a specific frame using composition data (I2I)."""
    try:
        logger.info(f"Rendering frame {request.frame_id}")

        updated_script = pipeline.generate_storyboard_render(
            script.id,
            request.frame_id,
            request.composition_data,
            request.prompt,
            request.batch_size
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Error rendering frame {request.frame_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SelectVideoRequest(BaseModel):
    video_id: str


@app.post("/projects/{script_id}/frames/{frame_id}/select_video")
def select_video(frame_id: str, request: SelectVideoRequest, script: Script = Depends(get_owned_script)):
    """Selects a video variant for a specific frame."""
    try:
        updated_script = pipeline.select_video_for_frame(script.id, frame_id, request.video_id)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/frames/{frame_id}/auto_select_latest_video")
def auto_select_latest_video(frame_id: str, script: Script = Depends(get_owned_script)):
    """Auto-pick the latest completed video as this frame's active take.

    Idempotent; skipped when the frame is pinned (is_video_pinned=True).
    Frontend calls this on every task-completion poll so the freshly
    generated take surfaces on the hero — unless the user has explicitly
    pinned a different take.
    """
    try:
        updated_script = pipeline.auto_select_latest_video(script.id, frame_id)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/frames/{frame_id}/unpin_video")
def unpin_video(frame_id: str, script: Script = Depends(get_owned_script)):
    """Clear the manual pin; auto_select_latest_video resumes on next poll.

    Leaves selected_video_id / video_url untouched — the user keeps seeing
    the current take until a new generation produces a newer completed
    task.
    """
    try:
        updated_script = pipeline.unpin_video(script.id, frame_id)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ExtractLastFrameRequest(BaseModel):
    video_task_id: str


@app.post("/projects/{script_id}/frames/{frame_id}/extract_last_frame")
def extract_last_frame(frame_id: str, request: ExtractLastFrameRequest, script: Script = Depends(get_owned_script)):
    """Extract the last frame from a completed video and add it as a variant to the frame's rendered_image_asset."""
    try:
        updated_script = pipeline.extract_last_frame(script.id, frame_id, request.video_task_id)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception(f"Error extracting last frame: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/frames/{frame_id}/upload_image")
def upload_frame_image(frame_id: str, file: UploadFile = File(...), grid_size: int = 0, grid_color: str = "black", script: Script = Depends(get_owned_script)):
    """Upload an image as a variant for a frame's rendered_image_asset."""
    try:
        # Save file locally first
        data, ext = validate_image_upload(file)
        data = apply_grid_overlay(data, ext, grid_size, grid_color)
        filename = f"{uuid.uuid4()}.{ext}"
        file_path = os.path.join("output/uploads", filename)

        with open(file_path, "wb") as buffer:
            buffer.write(data)

        updated_script = pipeline.upload_frame_image(script.id, frame_id, file_path, has_grid_overlay=grid_size > 0)
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error uploading frame image: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Issue 10: T2I 首帧 upload — uploaded image is appended to the frame's
# t2i_image_urls history and becomes the active首帧 immediately, unlocking
# Step 2 (I2V generation). Whitelisted formats + 8 MB cap reflect that this
# is a user-facing creator upload, not an arbitrary file store.
_T2I_UPLOAD_MAX_BYTES = 8 * 1024 * 1024
_T2I_UPLOAD_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@app.post("/projects/{script_id}/frames/{frame_id}/upload_t2i")
async def upload_t2i_frame(frame_id: str, file: UploadFile = File(...), grid_size: int = 0, grid_color: str = "black", script: Script = Depends(get_owned_script)):
    """Upload an external image as a T2I首帧 candidate for an I2V flow.

    Validation:
      - ≤ 8 MB (rejected with 413 to differentiate from validation 400)
      - jpg/jpeg/png/webp only (rejected with 415)

    On success, returns the updated StoryboardFrame so the client can read
    back `t2i_image_urls` and `t2i_selected_index` without an extra round-
    trip. The uploaded image becomes the active首帧 (auto-selected).
    """
    try:
        original_name = (file.filename or "").strip()
        if not original_name:
            raise HTTPException(status_code=400, detail="No filename provided")
        ext = os.path.splitext(original_name)[1].lower()
        if ext not in _T2I_UPLOAD_ALLOWED_EXTS:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type {ext!r}. Allowed: {sorted(_T2I_UPLOAD_ALLOWED_EXTS)}",
            )

        # Stream-to-disk with explicit byte cap so we never load >8 MB
        # into memory if a client lies about Content-Length.
        filename = f"t2i_{uuid.uuid4().hex}{ext}"
        rel_path = os.path.join("uploads", filename)
        abs_path = os.path.join("output", rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        size = 0
        try:
            with open(abs_path, "wb") as buffer:
                while chunk := await file.read(64 * 1024):
                    size += len(chunk)
                    if size > _T2I_UPLOAD_MAX_BYTES:
                        buffer.close()
                        os.unlink(abs_path)
                        raise HTTPException(
                            status_code=413,
                            detail=f"File exceeds {_T2I_UPLOAD_MAX_BYTES // (1024 * 1024)} MB limit",
                        )
                    buffer.write(chunk)
        except HTTPException:
            raise
        except Exception as e:
            # Clean up partial file on any unexpected error
            if os.path.exists(abs_path):
                try:
                    os.unlink(abs_path)
                except OSError:
                    pass
            raise HTTPException(status_code=500, detail=f"Upload write failed: {e}")

        if grid_size:
            with open(abs_path, "rb") as f:
                raw = f.read()
            gridded = apply_grid_overlay(raw, ext.lstrip("."), grid_size, grid_color)
            with open(abs_path, "wb") as f:
                f.write(gridded)

        # `pipeline.upload_t2i_frame` synchronously serializes + writes the
        # whole projects.json (~50-500KB) — wrap in to_thread so we don't
        # block the event loop for the ~50ms write. Matches the pattern
        # used by create_project / reparse_project / analyze_script_for_styles.
        loop = asyncio.get_event_loop()
        frame = await loop.run_in_executor(
            None,
            partial(pipeline.upload_t2i_frame, script.id, frame_id, rel_path),
        )
        if frame is None:
            # Roll back the file — frame/script gone, no reference will exist
            if os.path.exists(abs_path):
                try:
                    os.unlink(abs_path)
                except OSError:
                    pass
            raise HTTPException(status_code=404, detail="Script or frame not found")
        return signed_response(frame)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("upload_t2i_frame unexpected error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/merge")
def merge_videos(script: Script = Depends(get_owned_script)):
    """Merge all selected frame videos into final output"""
    import traceback
    try:
        merged_script = pipeline.merge_videos(script.id)
        return signed_response(merged_project_payload(merged_script))
    except ValueError as e:
        # Known validation errors (no videos, etc.)
        logger.error(f"[MERGE ERROR] Validation failed: {e}")
        logger.exception("An error occurred")
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # FFmpeg or processing errors
        logger.error(f"[MERGE ERROR] Runtime error: {e}")
        logger.exception("An error occurred")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"[MERGE ERROR] Unexpected error: {e}")
        logger.exception("An error occurred")
        raise HTTPException(status_code=500, detail=f"Merge failed: {str(e)}")


# ===== Export Endpoint =====

class ExportRequest(BaseModel):
    resolution: str = "1080p"
    format: str = "mp4"
    subtitles: str = "none"

@app.post("/projects/{script_id}/export")
def export_project(request: ExportRequest, script: Script = Depends(get_owned_script)):
    """Export project video by merging all selected frame videos.

    Currently delegates to the existing merge_videos pipeline.
    resolution/format/subtitles parameters are accepted but not yet applied
    (requires FFmpeg pipeline iteration).
    """
    try:
        # If already merged, return existing URL directly
        if script.merged_video_url:
            return signed_response({"url": script.merged_video_url})

        # Otherwise, run merge pipeline
        merged_script = pipeline.merge_videos(script.id)
        return signed_response({"url": merged_script.merged_video_url})
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"[EXPORT ERROR] {e}")
        logger.exception("An error occurred")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


# ===== Art Direction Endpoints =====

class AnalyzeStyleRequest(BaseModel):
    script_text: str


class SaveArtDirectionRequest(BaseModel):
    selected_style_id: str
    style_config: Dict[str, Any]
    custom_styles: List[Dict[str, Any]] = []
    ai_recommendations: List[Dict[str, Any]] = []


@app.post("/projects/{script_id}/art_direction/analyze")
async def analyze_script_for_styles(request: AnalyzeStyleRequest, script: Script = Depends(get_owned_script)):
    """Analyze script content and recommend visual styles using LLM"""
    try:
        # Use LLM to analyze and recommend styles (run in thread pool to avoid blocking, Python 3.8 compatible)
        custom_style = getattr(getattr(script, "prompt_config", None), "style_analysis", "")
        loop = asyncio.get_event_loop()
        recommendations = await loop.run_in_executor(
            None,  # Use default executor
            partial(pipeline.script_processor.analyze_script_for_styles, request.script_text, custom_style, user_id=script.owner_id or None)
        )

        return {"recommendations": recommendations}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.exception("An error occurred")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{script_id}/art_direction/clear")
def clear_project_art_direction(script: Script = Depends(get_owned_script)):
    """R2V v2 Phase 2 — clear project-level art_direction so the
    episode falls back to series baseline (inherit). Used by the
    Style step '重置为系列' button."""
    script_id = script.id
    script.art_direction = None
    script.updated_at = time.time()
    pipeline.scripts[script_id] = script
    pipeline._save_data()
    return signed_response(merged_project_payload(script))


@app.put("/projects/{script_id}/last_episode_summary")
def update_last_episode_summary(payload: dict, script: Script = Depends(get_owned_script)):
    """R2V v2 Phase P1-b — manually edit the cached AI summary.
    Body: {"ai_summary": "user-edited text"} or null to clear."""
    script_id = script.id
    summary = payload.get("ai_summary")
    if summary is None:
        script.last_episode_summary_cache = None
        script.last_episode_summary_revision = None
    else:
        script.last_episode_summary_cache = str(summary).strip()
        # When user manually edits, mark the revision as the current
        # previous-episode revision so it doesn't show stale.
        if script.series_id:
            series = pipeline.get_series(script.series_id)
            if series:
                try:
                    idx = series.episode_ids.index(script_id)
                    if idx > 0:
                        prev = pipeline.get_script(series.episode_ids[idx - 1])
                        if prev:
                            script.last_episode_summary_revision = _prev_text_revision(prev.original_text or "")
                except ValueError:
                    pass
    script.updated_at = time.time()
    pipeline.scripts[script_id] = script
    pipeline._save_data()
    return signed_response(merged_project_payload(script))


@app.post("/projects/{script_id}/art_direction/save")
def save_art_direction(request: SaveArtDirectionRequest, script: Script = Depends(get_owned_script)):
    """Save Art Direction configuration to the project"""
    try:
        updated_script = pipeline.save_art_direction(
            script.id,
            request.selected_style_id,
            request.style_config,
            request.custom_styles,
            request.ai_recommendations
        )
        return signed_response(merged_project_payload(updated_script))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback
        logger.exception("An error occurred")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/art_direction/presets")
def get_style_presets():
    """Get built-in style presets (v2: categories + presets)"""
    try:
        import json
        import os
        preset_file = os.path.join(os.path.dirname(__file__), "style_presets.json")

        if not os.path.exists(preset_file):
            return {"version": 2, "categories": [], "presets": []}

        with open(preset_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict) and data.get("version") == 2:
                return data
            # Legacy fallback: plain array
            return {"version": 2, "categories": [], "presets": data if isinstance(data, list) else []}
    except Exception as e:
        logger.exception("Failed to load style presets")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: /storyboard/polish_prompt removed - use /storyboard/refine_prompt instead


def _get_custom_prompt(script_id: str, field: str) -> str:
    """Read a custom prompt with 3-level fallback: Episode → Series → system default.
    Returns empty string if result equals system default (so LLM method uses its built-in)."""
    if not script_id:
        return ""
    script = pipeline.get_script(script_id)
    if not script:
        return ""
    series = pipeline.get_series(script.series_id) if script.series_id else None
    effective = pipeline.get_effective_prompt(field, script, series)
    # If it's the system default, return empty so the LLM method uses its built-in default
    from .llm import DEFAULT_STORYBOARD_POLISH_PROMPT, DEFAULT_VIDEO_POLISH_PROMPT, DEFAULT_R2V_POLISH_PROMPT
    defaults = {
        "storyboard_polish": DEFAULT_STORYBOARD_POLISH_PROMPT,
        "video_polish": DEFAULT_VIDEO_POLISH_PROMPT,
        "r2v_polish": DEFAULT_R2V_POLISH_PROMPT,
    }
    if effective == defaults.get(field, ""):
        return ""
    return effective


def _get_polish_model_for_project(script_id: str) -> str:
    """Read polish_model with 3-level fallback: Episode.prompt_config → Series.prompt_config → "".
    Empty = LLMAdapter uses its default (qwen3.6-plus). The frontend's polish-model dropdown
    in PromptConfig modal writes here; backend just reads."""
    if not script_id:
        return ""
    script = pipeline.get_script(script_id)
    if not script:
        return ""
    # Episode first
    ep_pc = getattr(script, "prompt_config", None)
    if ep_pc and getattr(ep_pc, "polish_model", ""):
        return ep_pc.polish_model
    # Series fallback
    if getattr(script, "series_id", None):
        series = pipeline.get_series(script.series_id)
        if series:
            s_pc = getattr(series, "prompt_config", None)
            if s_pc and getattr(s_pc, "polish_model", ""):
                return s_pc.polish_model
    return ""


class PolishVideoPromptRequest(BaseModel):
    draft_prompt: str
    feedback: str = Field("", max_length=2000)  # User feedback for iterative refinement
    script_id: str = ""  # Optional: project ID to load custom prompt config
    # 迭代时传入上一次的 CN 作为双语锚点，让模型同步修改双语；首次留空。
    prev_cn: str = ""
    # I2V 模式：首帧图 URL(s)。Vision-capable polish 模型会真正看见图像并
    # 用其指导润色（光影、构图、被摄主体等）。空列表 = 纯文本润色。
    image_urls: List[str] = Field(default_factory=list, max_length=4)
    # 显式覆盖 polish 用的 LLM 模型；空 = 用 project / series PromptConfig
    # 的 polish_model（再 fallback 到 system default）。
    polish_model: str = ""


def _polish_error_response(err) -> Dict[str, Any]:
    """把 PolishError 转成统一的 502 响应体。
    model_echo 时附带原文双语供前端做 warning 渲染。"""
    body: Dict[str, Any] = {
        "reason": err.reason,
        "message_zh": err.message_zh,
        "message_en": err.message_en,
    }
    if err.prompt_cn:
        body["prompt_cn"] = err.prompt_cn
    if err.prompt_en:
        body["prompt_en"] = err.prompt_en
    return body


@app.post("/video/polish_prompt")
def polish_video_prompt(request: PolishVideoPromptRequest, user=Depends(auth.require_login)):
    """Polishes a video generation prompt using LLM. Returns bilingual prompts.

    NOTE: Defined as a SYNC handler on purpose. The body calls
    `processor.polish_video_prompt()` which makes a blocking HTTP call to
    DashScope (openai sync client). If declared `async def`, FastAPI would
    run it on the event loop itself — blocking ALL other endpoints for the
    10-30s LLM call (e.g. concurrent `GET /prompt_config` from the modal
    looks "stuck loading"). Sync handlers get auto-dispatched to anyio's
    threadpool, freeing the event loop for other requests.

    成功：200 + {prompt_cn, prompt_en}
    失败：502 + {reason, message_zh, message_en, prompt_cn?, prompt_en?}
      其中 reason ∈ {is_configured_false, api_error, json_parse_error,
                     missing_keys, model_echo}。
      model_echo 是 warning 性质（带原文双语），其余是 hard error。
    """
    from .llm import PolishError
    try:
        custom_prompt = _get_custom_prompt(request.script_id, "video_polish")
        # Polish model: request override → project/series PromptConfig → ""
        polish_model = request.polish_model or _get_polish_model_for_project(request.script_id)
        processor = ScriptProcessor()
        result = processor.polish_video_prompt(
            request.draft_prompt,
            request.feedback,
            custom_prompt,
            request.prev_cn,
            image_urls=request.image_urls or None,
            polish_model=polish_model,
            user_id=user.id,
        )
        return {
            "prompt_cn": result.get("prompt_cn", ""),
            "prompt_en": result.get("prompt_en", "")
        }
    except PolishError as e:
        logger.warning("polish_video_prompt failed: %s", e)
        raise HTTPException(status_code=502, detail=_polish_error_response(e))
    except Exception as e:
        logger.exception("polish_video_prompt unexpected error")
        raise HTTPException(status_code=500, detail=str(e))


class RefSlot(BaseModel):
    description: str  # Character name, e.g., "雷震", "白兔"


class PolishR2VPromptRequest(BaseModel):
    draft_prompt: str
    slots: List[RefSlot]
    feedback: str = Field("", max_length=2000)  # User feedback for iterative refinement
    script_id: str = ""  # Optional: project ID to load custom prompt config
    prev_cn: str = ""  # 双语锚点迭代用，首次留空
    # R2V 模式：用户挂载的 character1/2/3 参考图 URL(s)，让 vision 模型
    # 看清各角色实际形象。空列表 = 纯文本润色（兼容旧调用方）。
    image_urls: List[str] = Field(default_factory=list, max_length=9)
    polish_model: str = ""


@app.post("/video/polish_r2v_prompt")
def polish_r2v_prompt(request: PolishR2VPromptRequest, user=Depends(auth.require_login)):
    """Polishes a R2V (Reference-to-Video) prompt using LLM. Returns bilingual prompts.
    错误约定同 /video/polish_prompt。
    SYNC handler on purpose — see polish_video_prompt for rationale."""
    from .llm import PolishError
    try:
        custom_prompt = _get_custom_prompt(request.script_id, "r2v_polish")
        polish_model = request.polish_model or _get_polish_model_for_project(request.script_id)
        processor = ScriptProcessor()
        slot_info = [{"description": s.description} for s in request.slots]
        result = processor.polish_r2v_prompt(
            request.draft_prompt,
            slot_info,
            request.feedback,
            custom_prompt,
            request.prev_cn,
            image_urls=request.image_urls or None,
            polish_model=polish_model,
            user_id=user.id,
        )
        return {
            "prompt_cn": result.get("prompt_cn", ""),
            "prompt_en": result.get("prompt_en", "")
        }
    except PolishError as e:
        logger.warning("polish_r2v_prompt failed: %s", e)
        raise HTTPException(status_code=502, detail=_polish_error_response(e))
    except Exception as e:
        logger.exception("polish_r2v_prompt unexpected error")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Environment Configuration Endpoints =====


# Credential-like env fields that must never be returned in plaintext.
SECRET_FIELDS = {
    "GEMINI_API_KEY",
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    "KLING_ACCESS_KEY",
    "KLING_SECRET_KEY",
    "VIDU_API_KEY",
    "ARK_API_KEY",
    "OPENAI_API_KEY",
}

# Bullet sentinel: never appears in a real key, so the save path can detect an
# unchanged (still-masked) field and avoid overwriting the stored secret.
_MASK_CHAR = "\u2022"


def _mask_secret(value: Optional[str]) -> str:
    """Return a masked representation (bullets + last 4 chars) for a configured
    secret, or an empty string when it is unset. Never reveals the full value."""
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= 4:
        return _MASK_CHAR * len(v)
    return _MASK_CHAR * 8 + v[-4:]


@app.get("/config/env")
def get_env_config():
    """Get current environment configuration.

    Secrets are masked (bullets + last 4 chars) and never returned in
    plaintext. `secrets_configured` reports which credential fields are set so
    the frontend can drive required-field / validation logic without the raw
    value. Non-secret config (OSS bucket/endpoint/base path, provider modes,
    endpoint overrides) is returned as-is."""
    try:
        from ...utils.endpoints import PROVIDER_DEFAULTS
        from ...utils.oss_utils import is_oss_enabled
        endpoint_overrides = {}
        for provider in PROVIDER_DEFAULTS:
            env_key = f"{provider}_BASE_URL"
            value = os.getenv(env_key)
            if value:
                endpoint_overrides[env_key] = value

        secrets_configured = {
            field: bool((os.getenv(field, "") or "").strip())
            for field in SECRET_FIELDS
        }

        return {
            # Masked secrets — never plaintext.
            "GEMINI_API_KEY": _mask_secret(os.getenv("GEMINI_API_KEY")),
            "ALIBABA_CLOUD_ACCESS_KEY_ID": _mask_secret(os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")),
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": _mask_secret(os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")),
            "KLING_ACCESS_KEY": _mask_secret(os.getenv("KLING_ACCESS_KEY")),
            "KLING_SECRET_KEY": _mask_secret(os.getenv("KLING_SECRET_KEY")),
            "VIDU_API_KEY": _mask_secret(os.getenv("VIDU_API_KEY")),
            "ARK_API_KEY": _mask_secret(os.getenv("ARK_API_KEY")),
            "OPENAI_API_KEY": _mask_secret(os.getenv("OPENAI_API_KEY")),
            # Non-secret config.
            "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "dashscope"),
            "ARK_REGION": os.getenv("ARK_REGION", ""),
            "ARK_BASE_URL": os.getenv("ARK_BASE_URL", ""),
            "OSS_BUCKET_NAME": os.getenv("OSS_BUCKET_NAME", ""),
            "OSS_ENDPOINT": os.getenv("OSS_ENDPOINT", ""),
            "OSS_BASE_PATH": os.getenv("OSS_BASE_PATH", ""),
            "OSS_ENABLE": is_oss_enabled(),
            "endpoint_overrides": endpoint_overrides,
            "secrets_configured": secrets_configured,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





# ============================================
# Prop CRUD Endpoints
# ============================================

class CreatePropRequest(BaseModel):
    name: str
    description: str = ""

@app.post("/projects/{script_id}/props")
def create_prop(request: CreatePropRequest, script: Script = Depends(get_owned_script)):
    """Creates a new prop in the project."""
    import uuid
    from .models import Prop, GenerationStatus

    new_prop = Prop(
        id=f"prop_{uuid.uuid4().hex[:8]}",
        name=request.name,
        description=request.description,
        status=GenerationStatus.PENDING
    )

    script.props.append(new_prop)
    script.updated_at = time.time()
    pipeline._save_data()

    return signed_response(merged_project_payload(script))


@app.delete("/projects/{script_id}/props/{prop_id}")
def delete_prop(prop_id: str, script: Script = Depends(get_owned_script)):
    """Deletes a prop from the project."""
    original_count = len(script.props)
    script.props = [p for p in script.props if p.id != prop_id]

    if len(script.props) == original_count:
        raise HTTPException(status_code=404, detail="Prop not found")

    # Remove prop references from frames
    for frame in script.frames:
        if prop_id in frame.prop_ids:
            frame.prop_ids.remove(prop_id)

    script.updated_at = time.time()
    pipeline._save_data()

    return signed_response(merged_project_payload(script))
