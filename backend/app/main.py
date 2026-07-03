"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.db import close_mongo_connection, connect_to_mongo, get_database
from app.models import user as user_model
from app.routes.auth import router as auth_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting DRRCS API (env=%s)", settings.app_env)
    await connect_to_mongo()
    # Ensure indexes only when Mongo is actually up. Errors are logged but not fatal.
    try:
        await user_model.ensure_indexes()
    except RuntimeError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skipping index ensure: %s", exc)
    try:
        yield
    finally:
        await close_mongo_connection()


app = FastAPI(title="DRRCS API", version="0.1.0", lifespan=lifespan)

# Routers
app.include_router(auth_router)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "service": "drrcs-api"}


@app.get("/health")
async def health():
    """Liveness + Mongo readiness probe."""
    mongo_status = "not_configured"
    try:
        db = get_database()
        await db.command("ping")
        mongo_status = "ok"
    except RuntimeError:
        mongo_status = "not_configured"
    except Exception as exc:  # noqa: BLE001
        mongo_status = f"error: {exc}"

    settings = get_settings()
    return {
        "status": "ok",
        "env": settings.app_env,
        "mongo": mongo_status,
    }
