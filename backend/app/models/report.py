"""Report document model and Mongo helpers.

One collection: `reports`. Each document stores the raw citizen input, the
list of stored image filenames, and a placeholder `ai_output` (null until
the AI service is wired in). `user_id` links the report to the citizen.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.core.db import get_database

COLLECTION = "reports"

# Pipeline lifecycle. Stored as the document's `status` field.
REPORT_STATUS_PENDING_AI = "pending_ai"
REPORT_STATUS_PROCESSED = "processed"
REPORT_STATUS_FAILED = "failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Mongo doc to a JSON-safe dict suitable for `ReportOut`."""
    raw_location = doc.get("location") or {}
    coords = raw_location.get("coords") or {}
    images = [
        {
            "filename": img.get("filename"),
            "url": f"/api/report/{str(doc['_id'])}/images/{img.get('filename')}",
            "size": img.get("size", 0),
            "content_type": img.get("content_type"),
        }
        for img in doc.get("images", [])
        if img.get("filename")
    ]
    return {
        "id": str(doc["_id"]),
        "user_id": str(doc["user_id"]),
        "description": doc.get("description", ""),
        "location": {
            "division": raw_location.get("division"),
            "district": raw_location.get("district"),
            "upazila": raw_location.get("upazila"),
            "area": raw_location.get("area"),
            "coords": {"lat": coords.get("lat"), "lng": coords.get("lng")} or None,
        },
        "affected_count": doc.get("affected_count"),
        "assistance": doc.get("assistance", []),
        "immediate_danger": bool(doc.get("immediate_danger", False)),
        "incident_time": doc.get("incident_time"),
        "notes": doc.get("notes"),
        "images": images,
        "status": doc.get("status", REPORT_STATUS_PENDING_AI),
        "ai_output": doc.get("ai_output"),
        "error": doc.get("error"),
        "submitted_at_client": doc.get("submitted_at_client"),
        "created_at": doc["created_at"].isoformat()
        if isinstance(doc.get("created_at"), datetime)
        else doc.get("created_at"),
        "updated_at": doc["updated_at"].isoformat()
        if isinstance(doc.get("updated_at"), datetime)
        else doc.get("updated_at"),
    }


async def ensure_indexes() -> None:
    """Indexes that keep queries cheap under hackathon load."""
    db = get_database()
    await db[COLLECTION].create_index("user_id")
    await db[COLLECTION].create_index([("created_at", -1)])
    await db[COLLECTION].create_index([("user_id", 1), ("created_at", -1)])
    # Geo index — required for $geoWithin bbox queries on LiveMap.
    # mongomock ignores this silently; real Mongo uses it.
    await db[COLLECTION].create_index([("location.coords", "2dsphere")])


async def create_report(
    *,
    user_id: str,
    payload: Dict[str, Any],
    images: List[Dict[str, Any]],
    status: str = REPORT_STATUS_PENDING_AI,
) -> Dict[str, Any]:
    """Insert a new report. Returns the serialized public dict.

    `payload` is the validated Pydantic data (raw input).
    `images` is a list of dicts: {filename, size, content_type}.
    """
    db = get_database()
    now = _utcnow()
    doc: Dict[str, Any] = {
        "user_id": ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id,
        "description": payload["description"],
        "location": payload["location"],
        "affected_count": payload.get("affected_count"),
        "assistance": payload.get("assistance", []),
        "immediate_danger": bool(payload.get("immediate_danger", False)),
        "incident_time": payload.get("incident_time"),
        "notes": payload.get("notes"),
        "images": images,
        "submitted_at_client": payload.get("submitted_at"),
        "status": status,
        "ai_output": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


async def find_by_id(report_id: str) -> Optional[Dict[str, Any]]:
    if not ObjectId.is_valid(report_id):
        return None
    db = get_database()
    doc = await db[COLLECTION].find_one({"_id": ObjectId(report_id)})
    return _serialize(doc) if doc else None


async def find_all(
    limit: int = 100,
    geo_filter: Optional[Dict[str, Any]] = None,
    extra_filter: Optional[Dict[str, Any]] = None,
    bbox: Optional[Dict[str, float]] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Latest-first list for the dashboard.

    `geo_filter` is a Mongo `$geoWithin` / `$near` clause to apply (e.g. a
    bbox polygon). `extra_filter` is an arbitrary Mongo filter merged on
    top (e.g. `{"created_at": {"$gte": cutoff_dt}}`). `bbox` is an
    optional dict `{west, south, east, north}`; if supplied we apply the
    Python-side bbox predicate on top of Mongo results so the same code
    works against real Mongo and mongomock (which lacks `$geoWithin`).
    `offset` skips that many items; combined with `limit` it forms a
    pagination cursor (cheap because there's no real-time < -order
    requirement).
    """
    db = get_database()
    base: Dict[str, Any] = {}
    if geo_filter:
        # Mongo requires `location.coords` to be wrapped; merge carefully.
        base["location.coords"] = geo_filter
    if extra_filter:
        base.update(extra_filter)
    # Fetch enough candidates that we can still satisfy offset+limit after
    # the Python-side bbox predicate trims out-of-rectangle items.
    fetch = (limit + offset) * 4 if bbox else (limit + offset)
    cursor = db[COLLECTION].find(base).sort("created_at", -1).limit(fetch)
    filtered: List[Dict[str, Any]] = []
    async for doc in cursor:
        ser = _serialize(doc)
        if bbox is not None and not _in_bbox(ser.get("location", {}).get("coords"), bbox):
            continue
        filtered.append(ser)
        if len(filtered) >= limit + offset:
            break
    # Apply offset + limit to the in-Python filtered list.
    return filtered[offset:offset + limit]


def _in_bbox(coords: Optional[Dict[str, Any]], bbox: Dict[str, float]) -> bool:
    """Python-side bbox predicate — safe fallback for mongomock.

    Real Mongo handles this via `$geoWithin`; mongomock does not.
    """
    if not coords:
        return False
    lat = coords.get("lat")
    lng = coords.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return False
    return (
        bbox["west"] <= lng <= bbox["east"]
        and bbox["south"] <= lat <= bbox["north"]
    )


async def find_image_filename(report_id: str, filename: str) -> Optional[Dict[str, Any]]:
    """Look up one image meta block; used by the GET-image endpoint.

    Implemented with a plain `find_one` (no positional projection) so it
    works under both PyMongo and mongomock.
    """
    if not ObjectId.is_valid(report_id):
        return None
    db = get_database()
    doc = await db[COLLECTION].find_one(
        {"_id": ObjectId(report_id), "images.filename": filename},
    )
    if not doc:
        return None
    for img in doc.get("images") or []:
        if img.get("filename") == filename:
            return {
                "filename": img.get("filename"),
                "size": img.get("size", 0),
                "content_type": img.get("content_type"),
            }
    return None


# --- AI helpers ------------------------------------------------------------
async def find_raw_by_id(report_id: str) -> Optional[Dict[str, Any]]:
    """Return the raw Mongo doc (not serialized) — for the AI pipeline."""
    if not ObjectId.is_valid(report_id):
        return None
    db = get_database()
    return await db[COLLECTION].find_one({"_id": ObjectId(report_id)})


async def set_ai_output(report_id: str, ai_output: Dict[str, Any]) -> None:
    if not ObjectId.is_valid(report_id):
        return
    db = get_database()
    now = _utcnow()
    await db[COLLECTION].update_one(
        {"_id": ObjectId(report_id)},
        {
            "$set": {
                "ai_output": ai_output,
                "status": REPORT_STATUS_PROCESSED,
                "error": None,
                "updated_at": now,
            }
        },
    )


async def set_status(
    report_id: str,
    *,
    new_status: str,
    notes: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Admin/manual status transition.

    Returns the updated serialized doc, or None if the id is invalid / not found.
    Records an audit entry in `status_log` so the dashboard can show who
    changed what and when.
    """
    if not ObjectId.is_valid(report_id):
        return None
    db = get_database()
    now = _utcnow()
    entry = {
        "at": now,
        "from_status": None,  # filled in by caller if they want a snapshot
        "to_status": new_status,
        "notes": notes,
        "actor_id": actor_id,
    }
    res = await db[COLLECTION].update_one(
        {"_id": ObjectId(report_id)},
        {
            "$set": {
                "status": new_status,
                "updated_at": now,
                # Clear AI error on any transition out of "failed".
                "error": None if new_status != REPORT_STATUS_FAILED else "manual_mark",
            },
            "$push": {"status_log": entry},
        },
    )
    if res.matched_count == 0:
        return None
    doc = await db[COLLECTION].find_one({"_id": ObjectId(report_id)})
    return _serialize(doc) if doc else None


# --- List helpers --------------------------------------------------------
async def count_all(
    *,
    geo_filter: Optional[Dict[str, Any]] = None,
    bbox: Optional[Dict[str, float]] = None,
    user_id: Optional[str] = None,
) -> int:
    """Total matching reports (ignores limit/offset) — used for pagination."""
    db = get_database()
    query: Dict[str, Any] = {}
    if user_id:
        # Stored as ObjectId in create_report; mirror that here.
        query["user_id"] = ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id
    if bbox:
        # Reports without coords are excluded by a bbox predicate at the
        # query layer: only ones whose lat/lng fall inside.
        # Same rule as `find_all`.
        query["location.coords.lat"] = {"$gte": bbox["south"], "$lte": bbox["north"]}
        query["location.coords.lng"] = {"$gte": bbox["west"], "$lte": bbox["east"]}
    return await db[COLLECTION].count_documents(query)


async def set_ai_failed(report_id: str, error: str) -> None:
    if not ObjectId.is_valid(report_id):
        return
    db = get_database()
    now = _utcnow()
    await db[COLLECTION].update_one(
        {"_id": ObjectId(report_id)},
        {
            "$set": {
                "status": REPORT_STATUS_FAILED,
                "error": error[:1000],
                "updated_at": now,
            }
        },
    )


async def find_recent_with_coords(
    *,
    since: datetime,
    limit: int = 5000,
) -> List[Dict[str, Any]]:
    """Raw docs (not serialized) that have coords and were created since `since`.

    Used by the hotspot service. We return RAW docs so the service can read
    `ai_output.combined.severity` etc. without paying serialization cost.
    """
    db = get_database()
    cursor = db[COLLECTION].find(
        {
            "created_at": {"$gte": since},
            "location.coords": {"$exists": True, "$ne": None},
        }
    ).limit(limit)
    out: List[Dict[str, Any]] = []
    async for doc in cursor:
        coords = (doc.get("location") or {}).get("coords") or {}
        if isinstance(coords.get("lat"), (int, float)) and isinstance(
            coords.get("lng"), (int, float)
        ):
            out.append(doc)
    return out


async def find_stale_pending(threshold_seconds: int) -> List[str]:
    """IDs of `pending_ai` docs older than threshold_seconds."""
    db = get_database()
    cutoff = _utcnow().timestamp() - threshold_seconds
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
    cursor = db[COLLECTION].find(
        {"status": REPORT_STATUS_PENDING_AI, "created_at": {"$lt": cutoff_dt}},
    )
    out: List[str] = []
    async for doc in cursor:
        out.append(str(doc["_id"]))
    return out