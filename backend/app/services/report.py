"""Report service: bridges the HTTP route and the Mongo model.

Two responsibilities:
1. Persist a new citizen report (with images on disk) — fast, returns 201.
2. Asynchronously run the AI pipeline in the background and update the
   stored document. Failures are caught and recorded, never re-raised.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import UploadFile

from app.ml import ai_pipeline
from app.models import report as report_model
from app.services import storage

logger = logging.getLogger(__name__)


async def submit_report(
    *,
    user: Dict[str, Any],
    payload: Dict[str, Any],
    images: Optional[List[UploadFile]] = None,
) -> Dict[str, Any]:
    """Save images, persist the report, kick off AI, return the public dict.

    The AI runs in a fire-and-forget background task — the caller does
    not wait for it. The route returns the 201 immediately.
    """
    saved_images: List[Dict[str, Any]] = []
    filenames_for_rollback: List[str] = []
    try:
        for upload in images or []:
            if not upload or not upload.filename:
                continue
            meta = await storage.save_upload(upload)
            saved_images.append(meta)
            filenames_for_rollback.append(meta["filename"])

        doc = await report_model.create_report(
            user_id=user["id"],
            payload=payload,
            images=saved_images,
        )

        # Schedule AI work without awaiting it.
        schedule_ai_processing(doc["id"])
        return doc
    except Exception:
        if filenames_for_rollback:
            storage.remove_uploads(filenames_for_rollback)
        raise


# --- Background AI coordination --------------------------------------------
def schedule_ai_processing(report_id: str) -> None:
    """Fire-and-forget AI task. Safe to call from sync or async contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Not inside a loop — skip (caller should have scheduled already).
        logger.warning("No running loop; AI not scheduled for %s", report_id)
        return
    loop.create_task(process_report_ai(report_id))


async def process_report_ai(report_id: str) -> None:
    """Load the report, run the AI pipeline, persist the result.

    Never raises — any exception is recorded on the document as
    `status='failed'` with `error=<message>`.
    """
    try:
        raw = await report_model.find_raw_by_id(report_id)
        if not raw:
            logger.warning("AI skipped: report %s not found", report_id)
            return

        # Guard against double-processing.
        if raw.get("status") in (
            report_model.REPORT_STATUS_PROCESSED,
        ):
            logger.info("AI skipped: report %s already processed", report_id)
            return

        # Run pipeline.
        ai_out = await ai_pipeline.process_report(raw)

        # Persist (clamp through Pydantic for safety).
        from app.schemas.report import AIOutput  # local import to avoid cycle
        validated = AIOutput(**ai_out)
        await report_model.set_ai_output(report_id, validated.model_dump())
        logger.info("AI processed report %s", report_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("AI failed for %s", report_id)
        try:
            await report_model.set_ai_failed(report_id, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("Could not record AI failure for %s", report_id)


async def reprocess_report(report_id: str) -> Optional[Dict[str, Any]]:
    """Admin-triggered retry. Returns the refreshed public dict."""
    await process_report_ai(report_id)
    return await report_model.find_by_id(report_id)


# --- Recovery (called from app lifespan) -----------------------------------
async def recover_pending() -> int:
    """Re-queue reports stuck in `pending_ai` past the threshold.

    Returns the number of reports scheduled.
    """
    from app.core.config import get_settings
    threshold = get_settings().ai_recovery_threshold_seconds
    ids = await report_model.find_stale_pending(threshold)
    for rid in ids:
        schedule_ai_processing(rid)
    if ids:
        logger.info("Recovered %s stale pending_ai reports", len(ids))
    return len(ids)