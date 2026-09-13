"""Image upload validation: real content sniffing, not filename/Content-Type trust.

Every upload endpoint saves an UploadFile straight to disk keyed off a
uuid4 filename, so path traversal isn't the risk here — an attacker
uploading an arbitrary payload with a `.png` extension is. This module
is the single place that decides "is this actually an image, and is it
small enough" before any bytes hit disk.
"""

from fastapi import UploadFile, HTTPException

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB — generous for reference photos, not for arbitrary blobs

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
