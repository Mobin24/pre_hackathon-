"""Relief matching endpoints.

Public surface:
- POST /api/match/{report_id}     auth required, returns ranked matches
- GET  /api/match/{report_id}/preview  auth required, dry-run summary

The match is built from the stored report (location, AI severity, requested
assistance) and the resources collection. Admins can override radius /
top-N via query params for the demo.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.routes.deps import get_current_user, require_db
from app.schemas.resource import MatchResult
from app.services import matching
from app.services import resource as resource_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["match"])


def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"success": False, "error": "Admin role required"},
        )


@router.post("/match/{report_id}", response_model=MatchResult)
async def match_report(
    report_id: str = Path(...),
    radius_km: float = Query(default=matching.DEFAULT_RADIUS_KM, ge=0.5, le=200),
    top_n: int = Query(default=3, ge=1, le=10),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> MatchResult:
    """Compute ranked matches for a report's incident.

    Citizens can match their own reports; admins can match any.
    """
    try:
        result = await resource_service.match_for_report(
            report_id, radius_km=radius_km, top_n=top_n
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Report not found"},
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": str(exc)},
        )
    return MatchResult(**result)


@router.get("/match/{report_id}/preview", response_model=MatchResult)
async def preview_match(
    report_id: str = Path(...),
    radius_km: float = Query(default=matching.DEFAULT_RADIUS_KM, ge=0.5, le=200),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> MatchResult:
    """Same as POST /api/match/{report_id} but read-only.

    Useful for the dashboard "preview" button without committing any state.
    """
    try:
        result = await resource_service.match_for_report(
            report_id, radius_km=radius_km, top_n=3
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Report not found"},
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "error": str(exc)},
        )
    return MatchResult(**result)