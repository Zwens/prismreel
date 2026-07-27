"""Containment check for stored, untrusted relative paths.

Lives here rather than in pipeline.py because the render engine needs the
same rule and importing pipeline from editing would be circular. There must
be exactly one implementation: a url resolved one way for the video and
another way for the subtitle track is how timelines desync.
"""

import os


def safe_resolve_path(base_dir: str, untrusted_rel: str) -> str:
    """Resolve *untrusted_rel* under *base_dir* and ensure it stays inside.

    Prevents path traversal (e.g. ``../../etc/passwd``).
    Returns the resolved absolute path; raises ValueError on escape attempts.
    """
    base = os.path.realpath(base_dir)
    resolved = os.path.realpath(os.path.join(base, untrusted_rel))
    if not resolved.startswith(base + os.sep) and resolved != base:
        raise ValueError(f"Path escapes base directory: {untrusted_rel}")
    return resolved
