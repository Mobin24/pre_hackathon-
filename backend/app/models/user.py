"""User document shape and Mongo helpers."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ASCENDING

from app.core.db import get_database

COLLECTION = "users"
VALID_ROLES: List[str] = ["citizen", "admin"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Mongo doc into a JSON-safe dict with string id.

    Includes the optional Bangladesh identity fields (nid, phone) so the
    frontend can rehydrate the session without losing data.
    """
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name"),
        "email": doc["email"],
        "nid": doc.get("nid"),
        "phone": doc.get("phone"),
        "role": doc["role"],
        "created_at": doc["created_at"].isoformat()
        if isinstance(doc.get("created_at"), datetime)
        else doc.get("created_at"),
        "updated_at": doc["updated_at"].isoformat()
        if isinstance(doc.get("updated_at"), datetime)
        else doc.get("updated_at"),
    }


async def ensure_indexes() -> None:
    """Create indexes required for auth.

    - `email` is unique (always present).
    - `nid` and `phone` have *partial* unique indexes that only apply when
      the field is set. Multiple users with `nid=None` / `phone=None` are
      allowed — required to make these fields truly optional.
    """
    db = get_database()
    await db[COLLECTION].create_index("email", unique=True)
    await db[COLLECTION].create_index(
        "nid",
        unique=True,
        partialFilterExpression={"nid": {"$type": "string"}},
    )
    await db[COLLECTION].create_index(
        "phone",
        unique=True,
        partialFilterExpression={"phone": {"$type": "string"}},
    )


async def create_user(
    full_name: str,
    email: str,
    password_hash: str,
    role: str = "citizen",
    nid: Optional[str] = None,
    phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert a new user. Raises ValueError on duplicate email/nid/phone."""
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}")
    db = get_database()
    now = _utcnow()
    doc: Dict[str, Any] = {
        "name": full_name.strip(),
        "email": email.lower().strip(),
        "password_hash": password_hash,
        "role": role,
        "created_at": now,
        "updated_at": now,
    }
    if nid:
        doc["nid"] = nid.strip()
    if phone:
        doc["phone"] = phone.strip()
    try:
        result = await db[COLLECTION].insert_one(doc)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        code = getattr(exc, "code", None)
        if "duplicate key" in msg or code == 11000:
            # Best-effort mapping of which key collided.
            if "email" in msg:
                raise ValueError("Email already registered") from exc
            if "nid" in msg:
                raise ValueError("NID already registered") from exc
            if "phone" in msg:
                raise ValueError("Phone already registered") from exc
            raise ValueError("User already registered") from exc
        raise
    doc["_id"] = result.inserted_id
    return _serialize(doc)


# --- Lookups ---------------------------------------------------------------
async def find_by_email(email: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    return await db[COLLECTION].find_one({"email": email.lower().strip()})


async def find_by_nid(nid: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    return await db[COLLECTION].find_one({"nid": nid.strip()})


async def find_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    return await db[COLLECTION].find_one({"phone": phone.strip()})


async def find_by_identifier(identifier: str) -> Optional[Dict[str, Any]]:
    """Try email → phone → nid lookups in order. First hit wins."""
    db = get_database()
    ident = identifier.strip()
    if not ident:
        return None
    # Email fast-path (cheap and the most common).
    user = await db[COLLECTION].find_one({"email": ident.lower()})
    if user:
        return user
    user = await db[COLLECTION].find_one({"phone": ident})
    if user:
        return user
    user = await db[COLLECTION].find_one({"nid": ident})
    return user


async def find_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    if not ObjectId.is_valid(user_id):
        return None
    db = get_database()
    return await db[COLLECTION].find_one({"_id": ObjectId(user_id)})