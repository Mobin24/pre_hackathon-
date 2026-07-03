"""User document shape and Mongo helpers."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.core.db import get_database

COLLECTION = "users"
VALID_ROLES: List[str] = ["citizen", "admin"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Mongo doc into a JSON-safe dict with string id."""
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "email": doc["email"],
        "role": doc["role"],
        "created_at": doc["created_at"].isoformat() if isinstance(doc.get("created_at"), datetime) else doc.get("created_at"),
        "updated_at": doc["updated_at"].isoformat() if isinstance(doc.get("updated_at"), datetime) else doc.get("updated_at"),
    }


async def ensure_indexes() -> None:
    """Create the unique-email index. Idempotent."""
    db = get_database()
    await db[COLLECTION].create_index("email", unique=True)


async def create_user(name: str, email: str, password_hash: str, role: str = "citizen") -> Dict[str, Any]:
    """Insert a new user. Raises ValueError if email already exists."""
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}")
    db = get_database()
    now = _utcnow()
    doc = {
        "name": name,
        "email": email.lower(),
        "password_hash": password_hash,
        "role": role,
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db[COLLECTION].insert_one(doc)
    except Exception as exc:  # noqa: BLE001
        # Duplicate key error (E11000) surfaces here.
        if "duplicate key" in str(exc).lower() or getattr(exc, "code", None) == 11000:
            raise ValueError("Email already registered") from exc
        raise
    doc["_id"] = result.inserted_id
    return _serialize(doc)


async def find_by_email(email: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    return await db[COLLECTION].find_one({"email": email.lower()})


async def find_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    if not ObjectId.is_valid(user_id):
        return None
    db = get_database()
    return await db[COLLECTION].find_one({"_id": ObjectId(user_id)})