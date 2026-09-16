"""Model ids retired by the DashScope removal, and how to migrate off them.

Deleting the wan / qwen-image / happyhorse / pixverse families leaves existing
projects pointing at ids the catalog no longer knows. Rather than fail at
generation time with "unknown model", projects are rewritten on read and saved
back, so a retired id survives exactly one version and this table can be
deleted later. Translating on every render instead would keep the table alive
forever.

Two rules govern the table:

* **Modality is preserved.** An i2v model maps to an i2v model. Downgrading
  video-edit to image-to-video, for instance, would silently produce something
  entirely different from what the shot was set up to do.
* **Unknown ids are returned untouched.** Guessing a replacement and swapping
  it in silently is worse than surfacing "this model was retired" — the user
  would believe the original model is still running.

`seedance-2.5-v2v` is a real target: probing Ark on 2026-09-08 showed all four
live Seedance models carry the `VideoEditing` task type. The catalog had simply
omitted v2v from `seedance.yaml`.
"""
from typing import Any, Dict, Optional, Tuple

# Keys of a mapping/JSON object whose *value* is a model id. Everything else is
# left alone, so a project titled "wan2.7-image-pro" keeps its title.
MODEL_FIELD_NAMES = frozenset({
    "model",
    "model_name",
    "image_model",
    "video_model",
    "t2i_model",
    "i2i_model",
    "i2v_model",
    "r2v_model",
    "t2v_model",
    "v2v_model",
})

_GEMINI_FLASH_IMAGE = "gemini-3.1-flash-image"
_GEMINI_PRO_IMAGE = "gemini-3-pro-image"

RETIRED_MODEL_MAP: Dict[str, str] = {
    # ── Images: wan / qwen-image → Gemini ──────────────────────────
    # pro tier maps to pro tier: 18 of the 28 existing references are
    # wan2.7-image-pro, and dropping them to flash would cost visible quality.
    "wan2.7-image-pro": _GEMINI_PRO_IMAGE,
    "qwen-image-2.0-pro": _GEMINI_PRO_IMAGE,
    "wan2.7-image": _GEMINI_FLASH_IMAGE,
    "wan2.6-t2i": _GEMINI_FLASH_IMAGE,
    "wan2.6-image": _GEMINI_FLASH_IMAGE,
    "wan2.5-t2i-preview": _GEMINI_FLASH_IMAGE,
    "wan2.5-i2i-preview": _GEMINI_FLASH_IMAGE,
    "wan2.2-t2i-plus": _GEMINI_FLASH_IMAGE,
    "wan2.2-t2i-flash": _GEMINI_FLASH_IMAGE,
    "qwen-image-2.0": _GEMINI_FLASH_IMAGE,

    # ── Video: wan / happyhorse / pixverse → Seedance ──────────────
    "wan2.7-i2v": "seedance-2.5-i2v",
    "wan2.7-r2v": "seedance-2.5-r2v",
    "wan2.7-t2v": "seedance-2.5-t2v",
    "wan2.6-i2v": "seedance-2.5-i2v",
    "wan2.6-r2v": "seedance-2.5-r2v",
    "wan2.5-i2v-preview": "seedance-2.5-i2v",
    "wan2.2-i2v-plus": "seedance-2.5-i2v",
    # fast tier maps to fast tier — these were chosen for speed, not quality.
    "wan2.6-i2v-flash": "seedance-2.0-fast-i2v",
    "wan2.2-i2v-flash": "seedance-2.0-fast-i2v",
    "happyhorse-1.0-i2v": "seedance-2.5-i2v",
    "happyhorse-1.0-r2v": "seedance-2.5-r2v",
    "happyhorse-1.0-t2v": "seedance-2.5-t2v",
    "pixverse-c1-i2v": "seedance-2.5-i2v",
    "pixverse-c1-r2v": "seedance-2.5-r2v",
    "pixverse-v5.6-r2v": "seedance-2.5-r2v",
    "pixverse-v4-i2v": "seedance-2.5-i2v",

    # ── Video editing (v2v) ───────────────────────────────────────
    "wan2.7-videoedit": "seedance-2.5-v2v",
    "happyhorse-1.0-video-edit": "seedance-2.5-v2v",

    # ── Container ids (family-level, slash-separated) ─────────────
    # These name a model line rather than a mode; i2v is the mode these lines
    # were overwhelmingly used in.
    "wan/wan2.7-video": "seedance-2.5-i2v",
    "wan/wan2.6-video": "seedance-2.5-i2v",
    "happyhorse/happyhorse-1.0-video": "seedance-2.5-i2v",
    "pixverse/pixverse-v6-video": "seedance-2.5-i2v",
    "pixverse/pixverse-c1-video": "seedance-2.5-i2v",
}


def migrate_model_id(model_id: Optional[str]) -> Optional[str]:
    """Return the replacement for a retired id, or the input unchanged."""
    if not model_id or not isinstance(model_id, str):
        return model_id
    return RETIRED_MODEL_MAP.get(model_id.strip(), model_id)


def migrate_project_models(payload: Any) -> Tuple[Any, bool]:
    """Rewrite every retired model id inside a loaded project.

    Walks the structure and only rewrites values under a key in
    ``MODEL_FIELD_NAMES``; free text and titles are untouched even when they
    happen to contain a retired id.

    Returns ``(new_payload, changed)``. The caller saves back only when
    ``changed`` is True — rewriting unconditionally would bump every project's
    mtime on every read. The input is never mutated, so a failure mid-walk
    cannot leave a project file half-migrated.
    """
    changed = False

    def walk(node: Any) -> Any:
        nonlocal changed
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                if key in MODEL_FIELD_NAMES and isinstance(value, str):
                    migrated = migrate_model_id(value)
                    if migrated != value:
                        changed = True
                    out[key] = migrated
                else:
                    out[key] = walk(value)
            return out
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(payload), changed
