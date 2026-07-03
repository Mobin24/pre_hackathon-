"""Situation report document model and Mongo helpers.

One collection: `sitreps`. Each document is an LLM-generated rollup of
incidents within a time window. Stored both the structured stats and the
free-text `summary` produced by the cheap summary model.

Document shape:
    {
        "_id": ObjectId,
        "window_start": datetime,
        "window_end": datetime,
        "scope": {"divisions": ["Dhaka"], "bbox": {...} or None},
        "stats": {
            "total_incidents": 87,
            "by_severity": {"critical": 3, "high": 7, ...},
            "by_type": {"flood": 42, ...},
            "by_division": {"Dhaka": 12, ...},
            "affected_people": 240,
            "assistance_counts": {"ambulance": 18, ...},
            "resource_availability": {"total": 40, "available": 30, "in_use": 10},
        },
        "headline": "3 critical flood zones in Sylhet, 120+ affected",
        "summary": "<2-3 sentence narrative>",
        "recommendations": ["...", "..."],
        "incidents_sampled": 20,    # how many reports fed the LLM (capped)
        "incident_ids": ["..", ".."], # stored ids used
        "model": "gpt-4o-mini",
        "model_status": "ok" | "fallback",
        "generated_at": datetime,
        "trigger": "manual" | "hourly_tick" | "api_request",
        "generated_by": "<user_id or 'system'>",
    }
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.core.db import get_database

COLLECTION = "sitreps"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "window_start": doc["window_start"].isoformat() if isinstance(doc.get("window_start"), datetime) else doc.get("window_start"),
        "window_end": doc["window_end"].isoformat() if isinstance(doc.get("window_end"), datetime) else doc.get("window_end"),
        "scope": doc.get("scope") or {},
        "stats": doc.get("stats") or {},
        "headline": doc.get("headline") or "",
        "summary": doc.get("summary") or "",
        "recommendations": doc.get("recommendations") or [],
        "incidents_sampled": doc.get("incidents_sampled", 0),
        "incident_ids": [str(x) for x in (doc.get("incident_ids") or [])],
        "model": doc.get("model"),
        "model_status": doc.get("model_status", "unknown"),
        "generated_at": doc["generated_at"].isoformat() if isinstance(doc.get("generated_at"), datetime) else doc.get("generated_at"),
        "trigger": doc.get("trigger", "manual"),
        "generated_by": doc.get("generated_by"),
    }


async def ensure_indexes() -> None:
    """Indexes that keep polling cheap."""
    db = get_database()
    await db[COLLECTION].create_index([("generated_at", -1)])
    await db[COLLECTION].create_index([("window_end", -1)])
    await db[COLLECTION].create_index([("scope.divisions", 1), ("generated_at", -1)])


async def create_sitrep(doc: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    full = {"created_at": _utcnow(), **doc}
    res = await db[COLLECTION].insert_one(full)
    full["_id"] = res.inserted_id
    return _serialize(full)


async def find_by_id(sitrep_id: str) -> Optional[Dict[str, Any]]:
    if not ObjectId.is_valid(sitrep_id):
        return None
    db = get_database()
    doc = await db[COLLECTION].find_one({"_id": ObjectId(sitrep_id)})
    return _serialize(doc) if doc else None


async def find_latest(scope_divisions: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    db = get_database()
    query: Dict[str, Any] = {}
    if scope_divisions:
        query["scope.divisions"] = {"$in": scope_divisions}
    doc = await db[COLLECTION].find_one(query, sort=[("generated_at", -1)])
    return _serialize(doc) if doc else None


async def find_recent(limit: int = 10, scope_divisions: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    db = get_database()
    query: Dict[str, Any] = {}
    if scope_divisions:
        query["scope.divisions"] = {"$in": scope_divisions}
    cursor = db[COLLECTION].find(query).sort("generated_at", -1).limit(limit)
    out: List[Dict[str, Any]] = []
    async for doc in cursor:
        out.append(_serialize(doc))
    return out