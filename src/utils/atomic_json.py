"""Atomic JSON persistence with rolling backups.

Replaces the previous `open(path, 'w') + json.dump` pattern, which left a
truncated file if the process died mid-write, and the `except: return {}`
load pattern, which caused the *next* write to overwrite the whole store
with an empty dict.
"""

import glob
import json
import os
import shutil
import time
from typing import Any, Optional

from . import get_logger

logger = get_logger(__name__)


class DataCorruptionError(Exception):
    """Raised when a store file exists but cannot be parsed.

    Callers MUST NOT swallow this. Starting with an empty store means the
    next save silently destroys every project on disk.
    """


def load_json_strict(path: str) -> Optional[Any]:
    """Load JSON from `path`.

    Returns None when the file does not exist (legitimate first-run state).
    Raises DataCorruptionError when the file exists but is unparseable.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        backups = _list_backups(path)
        hint = (
            f" Recent backups available: {', '.join(os.path.basename(b) for b in backups[:3])}"
            if backups
            else " No backups found."
        )
        raise DataCorruptionError(
            f"Failed to parse {path}: {e}.{hint} "
            f"Refusing to start with an empty store — fix or restore the file first."
        ) from e


def atomic_write_json(
    path: str,
    payload: Any,
    *,
    backup_interval_s: int = 300,
    backups: int = 10,
) -> None:
    """Write `payload` to `path` atomically, rotating a backup first.

    Temp file lands in the same directory so os.replace stays atomic
    (cross-filesystem rename is not).
    """
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)

    _maybe_backup(path, backup_interval_s=backup_interval_s, backups=backups)

    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _backup_glob(path: str) -> str:
    return f"{path}.bak.*"


def _list_backups(path: str) -> list:
    """Newest first."""
    return sorted(glob.glob(_backup_glob(path)), reverse=True)


def _maybe_backup(path: str, *, backup_interval_s: int, backups: int) -> None:
    if not os.path.exists(path) or backups <= 0:
        return

    existing = _list_backups(path)
    if existing and backup_interval_s > 0:
        try:
            if time.time() - os.path.getmtime(existing[0]) < backup_interval_s:
                return
        except OSError:
            pass

    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
    try:
        shutil.copy2(path, f"{path}.bak.{stamp}")
    except OSError as e:
        logger.warning(f"Backup of {path} failed (continuing with write): {e}")
        return

    for stale in _list_backups(path)[backups:]:
        try:
            os.remove(stale)
        except OSError:
            pass
