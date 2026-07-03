"""Real-time dashboard endpoints.

Public surface (admin-only except for the citizen's own data):
- GET  /api/dashboard/stats                     severity counts, resource counts
- GET  /api/dashboard/incidents                 ranked list (critical-first)
- GET  /api/dashboard/incidents/{id}            single incident for the modal
- POST /api/dashboard/incidents/{id}/dispatch   mark resource dispatched
- POST /api/dashboard/incidents/{id}/resolve    mark incident resolved
- GET  /api/dashboard/feed                      polling endpoint — combines stats

Polling cadence: the frontend calls `/api/dashboard/feed` every 5–10 seconds
to mirror "real-time" updates without websockets. Each call returns:
  - the latest stats,
  - the most recent N incidents,
  - the resources currently in use.

If we ever move to websockets, only the transport changes — the data
shapes here stay the same.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.db import get_database
from app.models import resource as resource_model
from app.models import report as report_model
from app.routes.deps import get_current_user, require_db
from app.schemas.resource import (
    ResourceListOut,
    ResourceOut,
)
from app.schemas.report import ReportListOut, ReportOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"success": False, "error": "Admin role required"},
        )


def _severity_rank(sev: str) -> int:
    """Numeric rank for sorting critical-first."""
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(sev).lower(), 4)


def _classify(severity: str, status: str) -> str:
    """Bucket a report for dashboard tiles."""
    if status == "resolved":
        return "resolved"
    if str(severity).lower() == "critical":
        return "critical"
    if str(severity).lower() == "high":
        return "high"
    return "active"


# --- /stats ----------------------------------------------------------------
@router.get("/stats")
async def dashboard_stats(
    window_hours: int = Query(default=24, ge=1, le=720),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
):
    """Aggregate counts for the dashboard top tiles.

    Returns:
      - total_incidents, by_severity, by_status
      - resource totals: total / available / in_use
      - active assignments count
      - last_updated (so the frontend knows it has fresh data)
    """
    _require_admin(current_user)
    db = get_database()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    # Incident counts
    incident_pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {
            "$group": {
                "_id": {
                    "sev": {"$ifNull": ["$ai_output.combined.severity", "unknown"]},
                    "status": {"$ifNull": ["$status", "pending_ai"]},
                },
                "n": {"$sum": 1},
            }
        },
    ]
    by_sev: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    async for row in db[report_model.COLLECTION].aggregate(incident_pipeline):
        _id = row["_id"]
        by_sev[_id["sev"]] = by_sev.get(_id["sev"], 0) + row["n"]
        # normalise the "resolved" pseudo-status
        st = _id["status"]
        if st == "processed":
            st = "processed"
        by_status[st] = by_status.get(st, 0) + row["n"]

    # Resource counts
    total_resources = await db[resource_model.COLLECTION].count_documents({})
    available_resources = await db[resource_model.COLLECTION].count_documents({"available": True})
    in_use_resources = total_resources - available_resources

    # Resource breakdown by type (so the dashboard can show "12 ambulances, 8 available")
    by_type_pipeline = [
        {"$group": {"_id": "$type", "total": {"$sum": 1}, "available": {"$sum": {"$cond": ["$available", 1, 0]}}}}
    ]
    resources_by_type: List[Dict[str, Any]] = []
    async for row in db[resource_model.COLLECTION].aggregate(by_type_pipeline):
        resources_by_type.append(
            {"type": row["_id"], "total": row["total"], "available": row["available"]}
        )
    resources_by_type.sort(key=lambda x: x["type"])

    return {
        "window_hours": window_hours,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "incidents": {
            "total": sum(by_sev.values()),
            "by_severity": by_sev,
            "by_status": by_status,
            "critical": by_sev.get("critical", 0),
            "high": by_sev.get("high", 0),
            "active": sum(v for k, v in by_sev.items() if k in ("critical", "high", "medium", "low")),
        },
        "resources": {
            "total": total_resources,
            "available": available_resources,
            "in_use": in_use_resources,
            "by_type": resources_by_type,
        },
        "actions": {
            "pending_dispatch": by_status.get("pending_ai", 0),
            "in_progress": by_status.get("processed", 0),
            "failed": by_status.get("failed", 0),
        },
    }


# --- /incidents (ranked list) ---------------------------------------------
@router.get("/incidents", response_model=ReportListOut)
async def dashboard_incidents(
    severity: Optional[str] = Query(default=None, description="critical|high|medium|low"),
    status_filter: Optional[str] = Query(default="active", alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100000),
    bbox: Optional[str] = Query(default=None, description="west,south,east,north"),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> ReportListOut:
    """Ranked, severity-first list of incidents.

    - severity=critical returns only critical; omit to return all.
    - status=active returns processed not-resolved; use 'all' for everything.
    - bbox limits results to a viewport rectangle (used by the live map).
    - offset + limit paginate the result; `total` is the *filtered*
      total — handy but not always trustworthy under heavy live writes.
    """
    _require_admin(current_user)
    db = get_database()

    query: Dict[str, Any] = {}
    if severity:
        query["ai_output.combined.severity"] = severity
    if status_filter == "active":
        query["status"] = {"$in": ["pending_ai", "processed"]}
        query.setdefault("resolved_at", {"$exists": False})
    elif status_filter and status_filter != "all":
        query["status"] = status_filter

    # Sort critical-first by adding a synthetic severity_rank before created_at.
    pipeline: List[Dict[str, Any]] = []
    if query:
        pipeline.append({"$match": query})
    pipeline.extend(
        [
            {
                "$addFields": {
                    "_sev_rank": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": [{"$ifNull": ["$ai_output.combined.severity", "medium"]}, "critical"]}, "then": 0},
                                {"case": {"$eq": [{"$ifNull": ["$ai_output.combined.severity", "medium"]}, "high"]}, "then": 1},
                                {"case": {"$eq": [{"$ifNull": ["$ai_output.combined.severity", "medium"]}, "medium"]}, "then": 2},
                                {"case": {"$eq": [{"$ifNull": ["$ai_output.combined.severity", "medium"]}, "low"]}, "then": 3},
                            ],
                            "default": 4,
                        }
                    }
                }
            },
            {"$sort": {"_sev_rank": 1, "created_at": -1}},
            # Fetch enough to cover offset + limit even after the bbox predicate trims.
            {"$limit": (limit + offset) * 4 if bbox else (limit + offset)},
        ]
    )

    raw_items: List[Dict[str, Any]] = []
    async for doc in db[report_model.COLLECTION].aggregate(pipeline):
        ser = report_model._serialize(doc)  # noqa: SLF001
        if bbox:
            from app.routes.report import _parse_bbox  # local import to avoid cycle
            spec = _parse_bbox(bbox)
            if spec and not report_model._in_bbox(  # noqa: SLF001
                ser.get("location", {}).get("coords"), spec["box"]
            ):
                continue
        raw_items.append(ser)

    total = len(raw_items)
    items = raw_items[offset:offset + limit]

    return ReportListOut(
        items=[ReportOut(**i) for i in items],
        count=len(items),
        total=total,
        offset=offset,
        limit=limit,
    )


# --- /incidents/{id} (single) ---------------------------------------------
@router.get("/incidents/{report_id}", response_model=ReportOut)
async def dashboard_incident_detail(
    report_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> ReportOut:
    _require_admin(current_user)
    doc = await report_model.find_by_id(report_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Incident not found"},
        )
    return ReportOut(**doc)


# --- /incidents/{id}/dispatch ---------------------------------------------
@router.post("/incidents/{report_id}/dispatch")
async def dispatch_resources(
    report_id: str,
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
):
    """Mark a set of resources as dispatched for this incident.

    Body:
        { "resource_ids": ["..", ".."], "notes": "..." }

    Side-effects:
      - sets `available: false` on each resource
      - appends a dispatch record on the incident doc
    """
    _require_admin(current_user)
    if not ObjectId.is_valid(report_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": "Invalid report id"},
        )

    resource_ids = payload.get("resource_ids") or []
    if not isinstance(resource_ids, list) or not resource_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": "resource_ids must be a non-empty list"},
        )
    notes = (payload.get("notes") or "").strip() or None

    db = get_database()
    report = await db[report_model.COLLECTION].find_one({"_id": ObjectId(report_id)})
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Incident not found"},
        )

    # Flip resources to unavailable
    object_ids = [ObjectId(rid) for rid in resource_ids if ObjectId.is_valid(rid)]
    if not object_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": "No valid resource ids"},
        )
    res = await db[resource_model.COLLECTION].update_many(
        {"_id": {"$in": object_ids}},
        {"$set": {"available": False, "updated_at": datetime.now(timezone.utc)}},
    )

    # Log the dispatch on the incident (audit trail + UI history)
    dispatch_entry = {
        "at": datetime.now(timezone.utc),
        "by": current_user.get("id"),
        "by_name": current_user.get("name"),
        "resource_ids": resource_ids,
        "notes": notes,
    }
    await db[report_model.COLLECTION].update_one(
        {"_id": ObjectId(report_id)},
        {
            "$push": {"dispatch_log": dispatch_entry},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )

    return {
        "success": True,
        "report_id": report_id,
        "dispatched": res.modified_count,
        "dispatched_at": dispatch_entry["at"].isoformat(),
    }


# --- /incidents/{id}/resolve ----------------------------------------------
@router.post("/incidents/{report_id}/resolve")
async def resolve_incident(
    report_id: str,
    payload: Optional[Dict[str, Any]] = None,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
):
    """Mark an incident resolved; optionally restore dispatched resources.

    Body (optional):
        { "restore_resources": true, "notes": "..." }
    """
    _require_admin(current_user)
    if not ObjectId.is_valid(report_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": "Invalid report id"},
        )

    payload = payload or {}
    restore = bool(payload.get("restore_resources", True))
    notes = (payload.get("notes") or "").strip() or None

    db = get_database()
    report = await db[report_model.COLLECTION].find_one({"_id": ObjectId(report_id)})
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Incident not found"},
        )

    restored = 0
    if restore:
        # Pull the resource IDs from the latest dispatch_log entry and free them.
        dispatch_log = report.get("dispatch_log") or []
        if dispatch_log:
            last_ids = [ObjectId(rid) for rid in dispatch_log[-1].get("resource_ids", []) if ObjectId.is_valid(rid)]
            if last_ids:
                upd = await db[resource_model.COLLECTION].update_many(
                    {"_id": {"$in": last_ids}},
                    {"$set": {"available": True, "updated_at": datetime.now(timezone.utc)}},
                )
                restored = upd.modified_count

    now = datetime.now(timezone.utc)
    await db[report_model.COLLECTION].update_one(
        {"_id": ObjectId(report_id)},
        {
            "$set": {
                "resolved_at": now,
                "resolved_by": current_user.get("id"),
                "resolution_notes": notes,
                "status": "resolved",
                "updated_at": now,
            }
        },
    )

    return {
        "success": True,
        "report_id": report_id,
        "resources_restored": restored,
        "resolved_at": now.isoformat(),
    }


# --- /feed -----------------------------------------------------------------
@router.get("/feed")
async def dashboard_feed(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
):
    """Polling endpoint for the dashboard: stats + recent incidents + resources.

    The frontend hits this every 5–10 seconds. We return enough to paint
    the entire dashboard without further round-trips.
    """
    _require_admin(current_user)

    # Delegate to the same data sources so /feed and /stats never diverge.
    stats = await dashboard_stats(
        window_hours=24,
        current_user=current_user,
        _=True,
    )
    incidents = await dashboard_incidents(
        severity=None,
        status_filter="active",
        limit=limit,
        bbox=None,
        current_user=current_user,
        _=True,
    )
    resources = await db_resources_list(
        available_only=True, limit=200, current_user=current_user, _=True
    )
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "incidents": incidents.dict(),
        "resources": resources.dict(),
    }


# --- Helper (kept local to avoid a circular import) -----------------------
async def db_resources_list(
    *, available_only: bool, limit: int,
    current_user: dict, _: bool,
) -> ResourceListOut:
    items, _ = await resource_model.find_all(
        available_only=available_only, limit=limit
    )
    return ResourceListOut(items=[ResourceOut(**i) for i in items], count=len(items))