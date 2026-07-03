"""Local filesystem image storage.

Each uploaded image is written to `backend/uploads/` with a uuid-prefixed
filename so collisions are impossible. The path is stored in the report
document; the public URL is served by `GET /api/report/{id}/images/{name}`.

This is intentionally minimal — for a real deployment swap this module
for S3/Cloudinary by changing only the `save_upload` and
`resolve_upload_path` functions.
"""
import os
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import UploadFile

# Absolute path to backend/uploads, created on first write.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BACKEND_ROOT / "uploads"

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/heic": ".heic",
}
MAX_IMAGE_BYTES = 6 * 1024 * 1024  # 6 MB per the frontend cap


def ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def resolve_upload_path(filename: str) -> Path:
    """Resolve a stored filename back to an absolute path, with traversal guard."""
    safe = Path(filename).name  # strip any directory parts
    candidate = (UPLOAD_DIR / safe).resolve()
    # Defense-in-depth: ensure we never escape UPLOAD_DIR.
    if UPLOAD_DIR.resolve() not in candidate.parents and candidate != UPLOAD_DIR:
        raise ValueError("Invalid filename")
    return candidate


async def save_upload(file: UploadFile) -> Dict[str, Any]:
    """Persist one uploaded image. Returns the meta dict to store in Mongo.

    Raises ValueError on bad mime / oversize file.
    """
    ensure_upload_dir()
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError(f"Unsupported image type: {content_type or 'unknown'}")

    blob = await file.read()
    if len(blob) == 0:
        raise ValueError("Empty file")
    if len(blob) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image too large: {len(blob)} bytes (max {MAX_IMAGE_BYTES})"
        )

    ext = ALLOWED_IMAGE_TYPES[content_type]
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / filename
    with open(dest, "wb") as fh:
        fh.write(blob)

    return {
        "filename": filename,
        "size": len(blob),
        "content_type": content_type,
    }


def remove_uploads(filenames: list[str]) -> None:
    """Best-effort cleanup. Errors are swallowed — DB row is the source of truth."""
    for name in filenames or []:
        try:
            p = resolve_upload_path(name)
            if p.exists():
                os.remove(p)
        except Exception:  # noqa: BLE001
            continue