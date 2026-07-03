"""Geo-intelligence endpoints (admin-only).

Public surface:
- GET /api/geo/hotspots?window=24h&grid=0.05&min_count=3    admin only

These complement the report list endpoint:
- GET /api/reports            → individual pins
- GET /api/geo/hotspots       → aggregated risk zones

See `docs/geo-flow.md` §3 for the algorithm and rationale.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.models import report as report_model
from app.routes.deps import get_current_user, require_db
from app.services import geo as geo_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/geo", tags=["geo"])


def _require_admin(current_user: dict) -> None:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"success": False, "error": "Admin role required"},
        )


@router.get("/hotspots")
async def get_hotspots(
    window: int = Query(default=24, ge=1, le=168, description="Hours of history to scan"),
    grid: float = Query(default=0.05, gt=0.0, le=1.0, description="Grid cell size in degrees (~5.5 km at 0.05)"),
    min_count: int = Query(default=3, ge=2, le=50, description="Min reports in a cell"),
    top_n: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
):
    """Detect high-risk zones from recent reports.

    Pure-Python grid-bucket aggregation. See `app.services.geo.detect_hotspots`.
    """
    _require_admin(current_user)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window)
    raw_docs = await report_model.find_recent_with_coords(since=cutoff)

    hotspots = geo_service.detect_hotspots(
        raw_docs,
        grid=grid,
        min_count=min_count,
        top_n=top_n,
    )
    return geo_service.build_hotspots_response(
        hotspots,
        window_hours=window,
    )