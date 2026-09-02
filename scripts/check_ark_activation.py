#!/usr/bin/env python3
"""Report which BytePlus Ark models this account has actually activated.

Ark separates two things that are easy to conflate: an API key's permission
scope, and per-model activation. A key with full platform permissions still
gets 404 `has not activated the model` until the account enables that model
service in the Ark console. `/api/v3/models` does not help — it is a public
catalog, not an entitlement list.

The probe sends a deliberately invalid request. Ark checks credentials and
model entitlement BEFORE parameter validation, so the response separates the
three cases without ever creating a task:

    "has not activated the model"  -> exists, not enabled for this account
    "does not exist"               -> wrong id, or invisible to this account
    anything else (e.g. 400)       -> reachable; the id and entitlement are fine

No task is created and nothing is billed.

Usage:
    python scripts/check_ark_activation.py
    python scripts/check_ark_activation.py --model dreamina-seedance-2-5-260628
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.byteplus import resolve_ark_base_url  # noqa: E402

VIDEO_PATH = "/contents/generations/tasks"
IMAGE_PATH = "/images/generations"

# Ark-side ids. Kept here rather than read from the catalog because the
# catalog still carries gateway-side ids for part of the Seedance family;
# once that migration lands this list should come from the catalog instead.
VIDEO_MODELS = (
    "dreamina-seedance-2-5-260628",
    "dreamina-seedance-2-0-260128",
    "dreamina-seedance-2-0-fast-260128",
    "dreamina-seedance-2-0-mini-260615",
    "seedance-1-5-pro-251215",
    "seedance-1-0-pro-250528",
    "seedance-1-0-pro-fast-251015",
)

IMAGE_MODELS = (
    "dola-seedream-5-0-pro-260628",
    "seedream-5-0-260128",
    "seedream-4-5-251128",
)

STATUS_ACTIVE = "OK"
STATUS_INACTIVE = "NOT ACTIVATED"
STATUS_MISSING = "NOT FOUND"
STATUS_ERROR = "PROBE FAILED"


def _read_api_key() -> str:
    """Env wins; fall back to .env so the script works before the app boots."""
    key = (os.getenv("ARK_API_KEY") or "").strip()
    if key:
        return key

    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "ARK_API_KEY":
                return value.strip().strip("\"'")
    return ""


def _classify(status_code: int, message: str) -> str:
    lowered = message.lower()
    if "has not activated" in lowered:
        return STATUS_INACTIVE
    if "does not exist" in lowered:
        return STATUS_MISSING
    if status_code in (200, 400, 422):
        return STATUS_ACTIVE
    return STATUS_ERROR


def _probe(base_url: str, key: str, path: str, payload: Dict) -> Tuple[str, str]:
    url = f"{base_url}{path}"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        return STATUS_ERROR, str(exc)[:120]

    try:
        message = response.json().get("error", {}).get("message", "")
    except ValueError:
        message = response.text[:200]

    return _classify(response.status_code, message), message[:120]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", help="Probe only these ids")
    args = parser.parse_args()

    key = _read_api_key()
    if not key:
        print("ARK_API_KEY not set (checked environment and .env).")
        return 2

    base_url = resolve_ark_base_url()
    print(f"Ark base URL : {base_url}")
    print(f"ARK_API_KEY  : set, ending {key[-4:]}\n")

    if args.model:
        targets: List[Tuple[str, str]] = [(mid, VIDEO_PATH) for mid in args.model]
    else:
        targets = [(mid, VIDEO_PATH) for mid in VIDEO_MODELS]
        targets += [(mid, IMAGE_PATH) for mid in IMAGE_MODELS]

    inactive = 0
    for model_id, path in targets:
        if path == VIDEO_PATH:
            # duration far outside every model's range, so a reachable model
            # answers with a parameter error rather than starting a task.
            payload = {
                "model": model_id,
                "content": [{"type": "text", "text": "probe"}],
                "duration": 9999,
            }
        else:
            payload = {"model": model_id, "prompt": "probe", "size": "999Z"}

        status, message = _probe(base_url, key, path, payload)
        if status == STATUS_INACTIVE:
            inactive += 1
        detail = "" if status == STATUS_ACTIVE else f"  {message}"
        print(f"{model_id:<36} {status:<14}{detail}")

    if inactive:
        print(
            f"\n{inactive} model(s) not activated. Enable them under "
            "Model activation in the Ark console, then re-run."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
