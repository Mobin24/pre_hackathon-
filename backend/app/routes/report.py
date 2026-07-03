"""Report endpoints.

Public surface:
- POST   /api/report/submit                  multipart, auth required (citizen)
- GET    /api/report/{id}                    auth required (owner or admin)
- GET    /api/reports                        auth required, latest first
- GET    /api/report/{id}/images/{name}      public, streams the stored image
- POST   /api/admin/reports/{id}/reprocess   admin only, re-runs AI pipeline

We deliberately accept multipart/form-data so the frontend can send files
in one call (option 1 from `docs/frontend-contract.md` §2.3).
"""
import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from app.models import report as report_model
from app.routes.deps import get_current_user, require_db
from app.schemas.report import (
    ReportListOut,
    ReportOut,
    ReportStatusUpdate,
    ReportSubmitRequest,
)
from app.services import report as report_service
from app.services import storage


def require_admin_role(current_user: dict) -> None:
    """Local helper used by admin endpoints."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"success": False, "error": "Admin role required"},
        )

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["reports"])

# Path → function map (kept explicit for clarity):
#   POST /api/report/submit              submit_report
#   GET  /api/report/{report_id}        get_report
#   GET  /api/reports                    list_reports
#   GET  /api/report/{id}/images/{name}  get_report_image


# --- Helpers ---------------------------------------------------------------
def _parse_form_json(value: Optional[str], field: str) -> Optional[dict]:
    """Parse a JSON-encoded form field; tolerate empty strings."""
    if value is None or value == "":
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"success": False, "error": f"{field} must be valid JSON: {exc}"},
        )
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"success": False, "error": f"{field} must be a JSON object"},
        )
    return parsed


def _parse_assistance(value: Optional[str]) -> List[str]:
    """`assistance` arrives as a JSON array string in form-data."""
    if value is None or value == "":
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        # Best effort: split on commas if the client forgot to JSON-encode.
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(parsed, list):
        return [str(v) for v in parsed]
    return []


# --- Rate-limit + dedupe --------------------------------------------------
# Lightweight, in-memory protection. Each user gets at most
# REPORT_RL_MAX submits in REPORT_RL_WINDOW seconds; identical payloads
# (same content-hash) inside REPORT_RL_DEDUPE_SECONDS are coalesced.
REPORT_RL_MAX = 5
REPORT_RL_WINDOW = 60.0  # 5 per minute
REPORT_RL_DEDUPE_SECONDS = 30.0

# user_id -> list[float]   (submit timestamps)
_rate_log: Dict[str, List[float]] = {}
# content_hash -> (timestamp, doc) — small window for rapid double-clicks.
_dedupe_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _enforce_rate_limit(user_id: str) -> None:
    now = time.monotonic()
    history = [t for t in _rate_log.get(user_id, []) if now - t < REPORT_RL_WINDOW]
    if len(history) >= REPORT_RL_MAX:
        retry_after = REPORT_RL_WINDOW - (now - history[0])
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "success": False,
                "error": "Too many reports submitted — please slow down.",
                "retry_after_seconds": int(retry_after) + 1,
            },
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    history.append(now)
    _rate_log[user_id] = history


def _dedupe_payload(payload_dict: dict) -> Optional[Dict[str, Any]]:
    """If the same JSON payload was submitted very recently, return the
    previous doc instead of double-writing. Keys include descriptions but
    exclude client-side volatile fields (image bytes / counts).
    """
    h = hashlib.sha256(
        json.dumps(payload_dict, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    now = time.monotonic()
    cached = _dedupe_cache.get(h)
    if cached and now - cached[0] < REPORT_RL_DEDUPE_SECONDS:
        return cached[1]
    # Periodic cleanup so the dict doesn't grow unbounded.
    cutoff = now - REPORT_RL_DEDUPE_SECONDS * 10
    for k in list(_dedupe_cache.keys()):
        if _dedupe_cache[k][0] < cutoff:
            _dedupe_cache.pop(k, None)
    return None


def _remember_payload(payload_dict: dict, doc: Dict[str, Any]) -> None:
    h = hashlib.sha256(
        json.dumps(payload_dict, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    _dedupe_cache[h] = (time.monotonic(), doc)


# --- POST /api/report/submit ----------------------------------------------
@router.post(
    "/report/submit",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_report(
    request: Request,
    description: str = Form(..., min_length=10, max_length=4000),
    location: str = Form(..., description="JSON-encoded location object"),
    affected_count: Optional[str] = Form(default=None),
    assistance: Optional[str] = Form(default=None),
    immediate_danger: Optional[str] = Form(default=None),
    incident_time: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    submitted_at: Optional[str] = Form(default=None),
    images: List[UploadFile] = File(default=[]),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> ReportOut:
    """Receive the form payload + images, persist, return public dict."""
    if current_user.get("role") != "citizen":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"success": False, "error": "Only citizens can submit reports"},
        )

    # Per-user rate-limit + content dedupe (rapid double-clicks).
    _enforce_rate_limit(str(current_user.get("id") or "anon"))

    location_dict = _parse_form_json(location, "location") or {}

    # Form fields come in as strings — coerce carefully for Pydantic.
    payload_dict: dict = {
        "description": description,
        "location": location_dict,
        "assistance": _parse_assistance(assistance),
        "immediate_danger": (str(immediate_danger).lower() == "true"),
        "incident_time": incident_time or None,
        "notes": notes or None,
        "submitted_at": submitted_at or None,
    }

    # affected_count: empty string → None; non-numeric → None (skip validation).
    if affected_count not in (None, ""):
        try:
            payload_dict["affected_count"] = int(affected_count)
        except (TypeError, ValueError):
            payload_dict["affected_count"] = None

    try:
        payload = ReportSubmitRequest(**payload_dict)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"success": False, "error": str(exc)},
        )

    canonical = payload.model_dump()
    deduped = _dedupe_payload(canonical)
    if deduped is not None:
        # Same payload within the dedupe window — return the existing doc.
        return ReportOut(**deduped)

    doc = await report_service.submit_report(
        user=current_user,
        payload=canonical,
        images=images or [],
    )
    _remember_payload(canonical, doc)
    return ReportOut(**doc)


# --- GET /api/report/{id} -------------------------------------------------
@router.get("/report/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> ReportOut:
    doc = await report_model.find_by_id(report_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Report not found"},
        )
    # Citizens can only see their own reports; admins see everything.
    if current_user.get("role") != "admin" and doc["user_id"] != current_user.get("id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"success": False, "error": "Forbidden"},
        )
    return ReportOut(**doc)


# --- PATCH /api/reports/{id}/status (admin) ------------------------------
# Allowed transitions:
#   processed -> resolved          (admin acknowledges completion)
#   pending_ai -> failed           (admin forces a failed mark)
#   failed -> pending_ai           (admin retries; the recovery sweep will pick it up)
#   processed -> pending_ai        (admin asks for a re-AI pass)
# Anything outside that set returns 409 Conflict.
ALLOWED_TRANSITIONS = {
    ("processed", "resolved"),
    ("pending_ai", "failed"),
    ("failed", "pending_ai"),
    ("processed", "pending_ai"),
}


@router.patch("/reports/{report_id}/status", response_model=ReportOut)
async def update_report_status(
    report_id: str,
    payload: ReportStatusUpdate,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> ReportOut:
    """Admin-only. Change a report's pipeline status.

    Returns the updated report so the dashboard can refresh its row
    without a second round-trip.
    """
    require_admin_role(current_user)

    doc = await report_model.find_by_id(report_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Report not found"},
        )

    from_status = (doc.get("status") or report_model.REPORT_STATUS_PENDING_AI).lower()
    new_status = payload.status

    if from_status == new_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": f"Report is already in status '{new_status}'"},
        )
    if (from_status, new_status) not in ALLOWED_TRANSITIONS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "success": False,
                "error": f"Cannot move report from '{from_status}' to '{new_status}'",
                "allowed_transitions_from_current": sorted(
                    t for (f, t) in ALLOWED_TRANSITIONS if f == from_status
                ),
            },
        )

    updated = await report_model.set_status(
        report_id,
        new_status=new_status,
        notes=payload.notes,
        actor_id=str(current_user.get("id") or ""),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Report not found after update"},
        )

    # Edge case: an admin pushing a previously-failed report back into
    # pending_ai should restart the AI pipeline so users see fresh output.
    if new_status == report_model.REPORT_STATUS_PENDING_AI:
        try:
            refreshed = await report_service.reprocess_report(report_id)
            if refreshed:
                updated = refreshed
        except Exception as exc:  # noqa: BLE001
            # Don't fail the status transition on a transient AI error —
            # the document is already updated; recovery sweep will retry.
            logger.warning("Post-transition reprocess failed: %s", exc)

    return ReportOut(**updated)


# --- GET /api/reports -----------------------------------------------------
# bbox format: "west,south,east,north" — 4 floats in WGS84.
_BBOX_REGEX = re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$")


def _parse_bbox(raw: Optional[str]) -> Optional[dict]:
    """Parse a bbox query string into both Mongo and Python predicates.

    Returns a dict with:
      - `mongo`: a `$geoWithin` polygon clause (used when Mongo supports it)
      - `box`:   the {west, south, east, north} dict used as a Python-side
                 predicate (works under mongomock which lacks geo support)
      - `polygon_coords`: the raw polygon ring (for tests / debugging)
    Returns None if `raw` is absent. Raises HTTPException(400) on bad input.
    """
    if raw is None or raw == "":
        return None
    if not _BBOX_REGEX.match(raw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": "bbox must be 'west,south,east,north' floats"},
        )
    w, s, e, n = (float(x) for x in raw.split(","))
    if not (-180 <= w <= 180 and -180 <= e <= 180 and -90 <= s <= 90 and -90 <= n <= 90):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": "bbox coordinates out of range"},
        )
    if w >= e or s >= n:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": "bbox is degenerate (west>=east or south>=north)"},
        )
    return {
        "box": {"west": w, "south": s, "east": e, "north": n},
        "mongo": {
            "$geoWithin": {
                "$geometry": {
                    "type": "Polygon",
                    "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
                }
            }
        },
    }


@router.get("/reports", response_model=ReportListOut)
async def list_reports(
    bbox: Optional[str] = Query(
        default=None,
        description="west,south,east,north in WGS84; limits results to a rectangle",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100000),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> ReportListOut:
    """Dashboard list. Citizens see their own; admins see everything.

    Optional `bbox` filter uses Mongo's `$geoWithin` — coordinates must be
    inside the rectangle. Reports without coords are excluded when a bbox
    is supplied (they can't be inside any rectangle).

    Pagination: `offset` + `limit`; response includes `total` (full match
    count) so the frontend can render "page X of Y" without a second trip.
    """
    bbox_spec = _parse_bbox(bbox)
    bbox_pred = bbox_spec["box"] if bbox_spec else None
    # We always use the Python-side bbox predicate. Real Mongo's `$geoWithin`
    # is more efficient, but mongomock doesn't implement it — so we keep one
    # code path. The 2dsphere index in `ensure_indexes` is still useful for
    # any future direct `$geoWithin` calls.
    geo_filter = None

    from app.core.db import get_database
    from bson import ObjectId

    db = get_database()
    is_admin = current_user.get("role") == "admin"

    if not is_admin:
        uid = current_user.get("id")
        if not uid or not ObjectId.is_valid(uid):
            return ReportListOut(items=[], count=0, total=0, offset=offset, limit=limit)
        # Citizens only see their own.
        items = await report_model.find_all(
            limit=limit,
            offset=offset,
            extra_filter={"user_id": ObjectId(uid)},
            bbox=bbox_pred,
        )
        total = await report_model.count_all(user_id=uid, bbox=bbox_pred)
    else:
        items = await report_model.find_all(
            limit=limit,
            offset=offset,
            geo_filter=geo_filter,
            bbox=bbox_pred,
        )
        total = await report_model.count_all(bbox=bbox_pred)

    return ReportListOut(
        items=[ReportOut(**i) for i in items],
        count=len(items),
        total=total,
        offset=offset,
        limit=limit,
    )


# --- GET /api/report/{id}/images/{filename} ------------------------------
@router.get("/report/{report_id}/images/{filename}")
async def get_report_image(
    report_id: str = Path(...),
    filename: str = Path(...),
):
    """Public — anyone with the URL can fetch the bytes (MVP).

    For production, swap for signed URLs from object storage.
    """
    meta = await report_model.find_image_filename(report_id, filename)
    if not meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Image not found"},
        )
    try:
        path = storage.resolve_upload_path(filename)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": "Invalid filename"},
        )
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Image file missing on disk"},
        )
    return FileResponse(
        path=path,
        media_type=meta.get("content_type") or "application/octet-stream",
        filename=filename,
    )


# --- Admin: reprocess ------------------------------------------------------
# Lives under the same router so /api/report/{id} is already wired up
# for share/authz. We require admin role for this one.
@router.post(
    "/admin/reports/{report_id}/reprocess",
    response_model=ReportOut,
)
async def admin_reprocess_report(
    report_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> ReportOut:
    require_admin_role(current_user)
    doc = await report_model.find_by_id(report_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Report not found"},
        )
    # Await so the admin sees the new AI state in the immediate response.
    refreshed = await report_service.reprocess_report(report_id)
    if not refreshed:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "error": "Reprocess failed"},
        )
    return ReportOut(**refreshed)