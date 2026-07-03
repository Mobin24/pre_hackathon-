"""MongoDB (Motor) connection management."""
import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConfigurationError, PyMongoError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None
_last_error: Optional[str] = None


def _is_placeholder(uri: str) -> bool:
    """Treat unfilled template values as 'not configured' so the app can boot."""
    if not uri:
        return True
    lowered = uri.lower()
    if "user:password" in lowered or "<" in uri or "xxxxx" in lowered:
        return True
    return False


async def connect_to_mongo() -> None:
    """Open the Motor client. Skips + warns on placeholder URIs; logs errors for real URIs but does not crash."""
    global _client, _db, _last_error

    settings = get_settings()

    if _is_placeholder(settings.mongodb_uri):
        _last_error = None
        logger.warning(
            "MONGODB_URI is not configured. Skipping Mongo connection. "
            "Set a real Atlas URI in backend/.env to enable persistence."
        )
        return

    try:
        _client = AsyncIOMotorClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=5000,
            uuidRepresentation="standard",
        )
        _db = _client[settings.mongodb_db_name]
        # Cheap ping so we fail fast if the cluster is unreachable.
        await _client.admin.command("ping")
        _last_error = None
        logger.info("MongoDB connected: db=%s", settings.mongodb_db_name)
    except (ConfigurationError, PyMongoError) as exc:
        _last_error = str(exc)
        logger.error("MongoDB connection failed: %s", exc)
        # Keep _client/_db as None so get_database() returns a clean error.
        _client = None
        _db = None


async def close_mongo_connection() -> None:
    """Close the Motor client on shutdown."""
    global _client, _db
    if _client is not None:
        _client.close()
        logger.info("MongoDB connection closed")
    _client = None
    _db = None


def get_database() -> AsyncIOMotorDatabase:
    """Return the active database handle. Raises if Mongo is not configured."""
    if _db is None:
        raise RuntimeError(
            "MongoDB is not configured or connection failed. "
            "Check MONGODB_URI in backend/.env."
        )
    return _db


def get_last_error() -> Optional[str]:
    return _last_error