"""FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.db import close_mongo_connection, connect_to_mongo, get_database
from app.models import report as report_model
from app.models import resource as resource_model
from app.models import sitrep as sitrep_model
from app.models import user as user_model
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.geo import router as geo_router
from app.routes.match import router as match_router
from app.routes.report import router as report_router
from app.routes.resource import router as resource_router
from app.routes.sitrep import router as sitrep_router
from app.services import report as report_service
from app.services import sitrep as sitrep_service
from app.services import storage

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
        logger.warning("Skipping user index ensure: %s", exc)
    try:
        await report_model.ensure_indexes()
    except RuntimeError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skipping report index ensure: %s", exc)
    try:
        await resource_model.ensure_indexes()
    except RuntimeError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skipping resource index ensure: %s", exc)
    try:
        await sitrep_model.ensure_indexes()
    except RuntimeError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skipping sitrep index ensure: %s", exc)
    # Local image storage directory.
    try:
        storage.ensure_upload_dir()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not create upload dir: %s", exc)
    # Recover reports that were left in pending_ai (e.g. after a crash).
    # Re-queues them via the same fire-and-forget path used by submit.
    try:
        recovered = await report_service.recover_pending()
        if recovered:
            logger.info("Re-queued %d pending AI reports on startup", recovered)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI recovery sweep failed: %s", exc)
    # Hourly auto-tick: produce a fresh global sitrep while the app lives.
    # Interval is configurable via SITREP_TICK_SECONDS (default 3600s = 1 hour).
    tick_seconds = float(getattr(settings, "sitrep_tick_seconds", 3600) or 3600)
    if tick_seconds <= 0:
        tick_seconds = 3600.0

    async def _sitrep_tick_loop() -> None:
        # Give the rest of startup a small grace window before first tick so
        # reports recovered above + first admin can settle.
        await asyncio.sleep(min(60.0, tick_seconds))
        while True:
            try:
                doc = await sitrep_service.generate_sitrep(
                    window_hours=24, trigger="hourly_tick", user_id="system"
                )
                logger.info(
                    "Hourly sitrep generated: id=%s headline=%r status=%s",
                    doc.get("id"),
                    doc.get("headline"),
                    doc.get("model_status"),
                )
            except Exception as exc:  # noqa: BLE001
                # Never let the tick crash the app.
                logger.warning("Hourly sitrep tick failed: %s", exc)
            await asyncio.sleep(tick_seconds)

    tick_task = asyncio.create_task(_sitrep_tick_loop())
    try:
        yield
    finally:
        tick_task.cancel()
        try:
            await tick_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        await close_mongo_connection()


app = FastAPI(title="DRRCS API", version="0.1.0", lifespan=lifespan)

# Routers
app.include_router(auth_router)
app.include_router(report_router)
app.include_router(geo_router)
app.include_router(resource_router)
app.include_router(match_router)
app.include_router(dashboard_router)
app.include_router(sitrep_router)

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
