"""Situation-report endpoints — admin-only.

POST /api/sitrep/generate      -> build a new sitrep now
GET  /api/sitrep/latest        -> most recent one (optional ?divisions=)
GET  /api/sitrep               -> recent list
GET  /api/sitrep/{id}          -> single
GET  /api/sitrep/{id}/export   -> download text or pdf
"""
from __future__ import annotations

import io
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.routes.deps import get_current_user, require_db
from app.schemas.sitrep import (
    SitrepGenerateRequest,
    SitrepListOut,
    SitrepOut,
)
from app.services import sitrep as sitrep_service

router = APIRouter(prefix="/api/sitrep", tags=["sitrep"])


# --- helpers -------------------------------------------------------------
def _require_admin(user: dict) -> None:
    if (user or {}).get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"success": False, "error": "Admin role required"},
        )


def _user_id(user: dict) -> Optional[str]:
    u = user or {}
    return str(u.get("id") or u.get("_id") or "") or None


# --- endpoints -----------------------------------------------------------
@router.post(
    "/generate",
    response_model=SitrepOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new situation report (admin)",
)
async def generate_sitrep(
    payload: SitrepGenerateRequest = SitrepGenerateRequest(),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
):
    _require_admin(current_user)
    doc = await sitrep_service.generate_sitrep(
        window_hours=payload.window_hours,
        divisions=payload.divisions or None,
        max_incidents=payload.max_incidents_to_summarize,
        trigger=payload.trigger,
        user_id=_user_id(current_user),
    )
    return SitrepOut(**doc)


@router.get(
    "/latest",
    response_model=SitrepOut,
    summary="Get the latest sitrep (admin, optional division filter)",
)
async def latest_sitrep(
    divisions: Optional[List[str]] = Query(default=None),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
):
    _require_admin(current_user)
    doc = await sitrep_service.latest_sitrep(divisions=divisions)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "No sitrep has been generated yet."},
        )
    return SitrepOut(**doc)


@router.get(
    "",
    response_model=SitrepListOut,
    summary="Recent sitreps (admin)",
)
async def list_sitreps(
    limit: int = Query(default=10, ge=1, le=100),
    divisions: Optional[List[str]] = Query(default=None),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
):
    _require_admin(current_user)
    docs = await sitrep_service.list_sitreps(limit=limit, divisions=divisions)
    return SitrepListOut(
        items=[SitrepOut(**d) for d in docs],
        count=len(docs),
    )


@router.get(
    "/{sitrep_id}",
    response_model=SitrepOut,
    summary="Fetch a single sitrep (admin)",
)
async def get_sitrep(
    sitrep_id: str,
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
):
    _require_admin(current_user)
    doc = await sitrep_service.get_sitrep(sitrep_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": f"Sitrep '{sitrep_id}' not found."},
        )
    return SitrepOut(**doc)


@router.get(
    "/{sitrep_id}/export",
    summary="Download sitrep as text or PDF (admin)",
    response_class=StreamingResponse,
)
async def export_sitrep(
    sitrep_id: str,
    format: str = Query(default="pdf", pattern="^(pdf|text)$"),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
):
    _require_admin(current_user)
    doc = await sitrep_service.get_sitrep(sitrep_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": f"Sitrep '{sitrep_id}' not found."},
        )

    if format == "text":
        body = sitrep_service.render_text(doc).encode("utf-8")
        return StreamingResponse(
            io.BytesIO(body),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="sitrep-{sitrep_id}.txt"'},
        )

    pdf_bytes = sitrep_service.render_pdf(doc)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="sitrep-{sitrep_id}.pdf"'},
    )
