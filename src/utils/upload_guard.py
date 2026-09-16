"""Upload validation: real content sniffing, not filename/Content-Type trust.

Every upload endpoint saves an UploadFile straight to disk keyed off a
uuid4 filename, so path traversal isn't the risk here — an attacker
uploading an arbitrary payload with a `.png` extension is. This module
is the single place that decides "is this actually the media type we
expect, and is it small enough" before any bytes hit disk.
"""

import os

from fastapi import UploadFile, HTTPException

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB — generous for reference photos, not for arbitrary blobs

# Videos get their own, much larger cap. A reference dance clip is seconds
# long, but phone footage is routinely 50-100 MB for that, and unlike a
# reference photo we never hold it in memory (see save_video_upload).
MAX_VIDEO_UPLOAD_BYTES = 200 * 1024 * 1024

# Magic-byte signatures for the formats the pipeline actually consumes
# (reference photos / uploaded frames). Anything else is rejected regardless
# of the extension or the client-supplied Content-Type header.
_SIGNATURES = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",  # narrowed below (RIFF is also used by WAV/AVI)
}


def _sniff_image_ext(head: bytes) -> str | None:
    for sig, ext in _SIGNATURES.items():
        if head.startswith(sig):
            if ext == "webp":
                return "webp" if head[8:12] == b"WEBP" else None
            return ext
    return None


def validate_image_upload(file: UploadFile) -> tuple[bytes, str]:
    """Read *file* fully while enforcing the size cap, then verify it's a real image.

    Returns (raw_bytes, sniffed_extension). Raises HTTPException(400/413) on
    anything that isn't a recognized image or exceeds MAX_UPLOAD_BYTES.
    """
    chunks = []
    total = 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024*1024)}MB limit")
        chunks.append(chunk)

    data = b"".join(chunks)
    ext = _sniff_image_ext(data[:16])
    if ext is None:
        raise HTTPException(status_code=400, detail="File is not a recognized image format (jpg/png/gif/webp)")
    return data, ext


# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------

def _sniff_video_ext(head: bytes) -> str | None:
    """Identify a container from its first bytes.

    ISO-BMFF (mp4/mov/m4v) is identified by the ``ftyp`` box at offset 4 rather
    than a leading signature, so it can't join the image signature table.
    """
    if len(head) < 12:
        return None
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        return "mov" if brand in (b"qt  ",) else "mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):  # EBML — webm / mkv
        return "webm"
    if head.startswith(b"RIFF") and head[8:12] == b"AVI ":
        return "avi"
    return None


def save_video_upload(file: UploadFile, dest_path_without_ext: str) -> str:
    """Stream *file* to disk, enforcing the size cap, and verify it's a video.

    Returns the final path (extension decided by content sniffing, not by the
    client-supplied filename). Unlike the image path this never buffers the
    whole upload in memory — a 200 MB cap held in RAM per concurrent upload is
    how a single user knocks the backend over.
    """
    head = file.file.read(32)
    ext = _sniff_video_ext(head)
    if ext is None:
        raise HTTPException(
            status_code=400,
            detail="File is not a recognized video format (mp4/mov/webm/avi)",
        )

    dest = f"{dest_path_without_ext}.{ext}"
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    total = len(head)
    try:
        with open(dest, "wb") as out:
            out.write(head)
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_VIDEO_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Video exceeds {MAX_VIDEO_UPLOAD_BYTES // (1024*1024)}MB limit",
                    )
                out.write(chunk)
    except Exception:
        # Don't leave a truncated or oversized file behind for the pipeline to
        # pick up later and fail on in a much more confusing place.
        if os.path.exists(dest):
            os.remove(dest)
        raise

    return dest
