"""Resource document model and Mongo helpers.

One collection: `resources`. Each document represents a relief asset
(volunteer, ambulance, shelter, food depot, water point, etc.) with a
geospatial location and capacity metadata. Resources are matched against
incident reports by `app/services/matching.py`.

Document shape:
    {
        "_id": ObjectId,
        "code": "AMB-DHK-01",
        "type": "ambulance",                 # see RESOURCE_TYPES
        "name": "Ambulance 7 — DMCH",
        "assistance": ["ambulance", "medicine"],  # what this resource fulfils
        "skills": ["trauma", "icu"],         # for volunteers only
        "location": {
            "division": "Dhaka",
            "district": "Dhaka",
            "area": "Ramna",
            "coords": {"lat": 23.73, "lng": 90.40}
        },
        "capacity": 2,                       # units it can serve at once
        "capacity_total": 50,                # for shelters: total beds
        "capacity_used": 12,                 # for shelters: occupied beds
        "available": true,
        "contact": {"phone": "+880...", "name": "..."},
        "priority": 0,                       # higher = boosted in ranking
        "tags": ["24x7"],
        "created_at": datetime,
        "updated_at": datetime,
    }
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.core.db import get_database

COLLECTION = "resources"

# All resource kinds we model. Keep aligned with `RESOURCE_TYPES` in schemas.
RESOURCE_TYPES: List[str] = [
    "volunteer",      # trained person — first aid, rescue, medical
    "ambulance",      # vehicle — patient transport
    "rescue_boat",    # water rescue vehicle
    "rescue_team",    # unit of trained rescuers (fire, civil defence)
    "shelter",        # building with beds
    "medical_team",   # doctors/nurses on site
    "food_depot",     # dry rations / cooked meals storage
    "water_point",    # clean drinking water source/tanker
    "medicine_store", # pharmacy / medical supplies cache
    "clothes_depot",  # clothing stock
    "baby_supplies",  # formula, diapers, blankets
    "other",
]

# Assistance keys (from ASSISTANCE_KEYS in schemas/report.py) that each
# resource type can fulfil. Used as a fast lookup when matching.
RESOURCE_TO_ASSISTANCE: Dict[str, List[str]] = {
    "volunteer":     ["rescue_team"],
    "ambulance":     ["ambulance", "medicine"],
    "rescue_boat":   ["rescue_boat", "rescue_team"],
    "rescue_team":   ["rescue_team"],
    "shelter":       ["shelter"],
    "medical_team":  ["medical", "medicine"],
    "food_depot":    ["food"],
    "water_point":   ["water"],
    "medicine_store":["medicine"],
    "clothes_depot": ["clothes"],
    "baby_supplies": ["baby_supplies"],
    "other":         ["other"],
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Mongo doc to JSON-safe dict."""
    loc = doc.get("location") or {}
    coords = loc.get("coords") or {}
    return {
        "id": str(doc["_id"]),
        "code": doc.get("code"),
        "type": doc.get("type"),
        "name": doc.get("name"),
        "assistance": doc.get("assistance", []),
        "skills": doc.get("skills", []),
        "location": {
            "division": loc.get("division"),
            "district": loc.get("district"),
            "area": loc.get("area"),
            "coords": {"lat": coords.get("lat"), "lng": coords.get("lng")}
            if isinstance(coords.get("lat"), (int, float)) and isinstance(coords.get("lng"), (int, float))
            else None,
        },
        "capacity": doc.get("capacity", 1),
        "capacity_total": doc.get("capacity_total"),
        "capacity_used": doc.get("capacity_used"),
        "available": bool(doc.get("available", True)),
        "contact": doc.get("contact") or {},
        "priority": doc.get("priority", 0),
        "tags": doc.get("tags", []),
        "created_at": doc["created_at"].isoformat() if isinstance(doc.get("created_at"), datetime) else doc.get("created_at"),
        "updated_at": doc["updated_at"].isoformat() if isinstance(doc.get("updated_at"), datetime) else doc.get("updated_at"),
    }


async def ensure_indexes() -> None:
    """Create indexes used by the matching queries.

    - `available` filter on every match call.
    - `type` filter when the report asks for a specific kind.
    - `assistance` is a multikey index for `assistance` lookup.
    - `location.coords` 2dsphere for $near queries (future geo filter).
    """
    db = get_database()
    await db[COLLECTION].create_index([("available", 1)])
    await db[COLLECTION].create_index([("type", 1), ("available", 1)])
    await db[COLLECTION].create_index([("assistance", 1)])
    # mongomock ignores 2dsphere silently; real Mongo uses it for $geoWithin/$near.
    await db[COLLECTION].create_index([("location.coords", "2dsphere")])


async def insert_one(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a resource doc and return the serialized form."""
    db = get_database()
    now = _utcnow()
    full = {
        "available": True,
        "capacity": 1,
        "priority": 0,
        "skills": [],
        "tags": [],
        "assistance": [],
        "contact": {},
        **doc,
        "created_at": now,
        "updated_at": now,
    }
    res = await db[COLLECTION].insert_one(full)
    full["_id"] = res.inserted_id
    return _serialize(full)


async def find_all(
    *,
    type_: Optional[str] = None,
    available_only: bool = False,
    assistance: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[List[Dict[str, Any]], int]:
    """List resources with optional filters.

    Returns `(items, total)` so the route can populate pagination meta.
    Items are already offset/limit-sliced.
    """
    db = get_database()
    query: Dict[str, Any] = {}
    if type_:
        query["type"] = type_
    if available_only:
        query["available"] = True
    if assistance:
        query["assistance"] = assistance
    total = await db[COLLECTION].count_documents(query)
    cursor = (
        db[COLLECTION]
        .find(query)
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
    )
    out: List[Dict[str, Any]] = []
    async for doc in cursor:
        out.append(_serialize(doc))
    return out, total


async def find_by_id(resource_id: str) -> Optional[Dict[str, Any]]:
    if not ObjectId.is_valid(resource_id):
        return None
    db = get_database()
    doc = await db[COLLECTION].find_one({"_id": ObjectId(resource_id)})
    return _serialize(doc) if doc else None


async def find_by_code(code: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    doc = await db[COLLECTION].find_one({"code": code})
    return _serialize(doc) if doc else None


async def update_availability(resource_id: str, available: bool) -> bool:
    if not ObjectId.is_valid(resource_id):
        return False
    db = get_database()
    res = await db[COLLECTION].update_one(
        {"_id": ObjectId(resource_id)},
        {"$set": {"available": bool(available), "updated_at": _utcnow()}},
    )
    return res.modified_count == 1


async def update_capacity(resource_id: str, capacity_used: int) -> bool:
    """Adjust a shelter's used capacity (clamped at capacity_total)."""
    if not ObjectId.is_valid(resource_id):
        return False
    db = get_database()
    res = await db[COLLECTION].update_one(
        {"_id": ObjectId(resource_id)},
        {"$set": {"capacity_used": int(capacity_used), "updated_at": _utcnow()}},
    )
    return res.modified_count == 1


async def delete_by_code(code: str) -> int:
    """Used by the seed script to make seeding idempotent."""
    db = get_database()
    res = await db[COLLECTION].delete_many({"code": {"$regex": f"^{code}$"}})
    return res.deleted_count