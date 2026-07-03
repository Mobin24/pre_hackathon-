"""Resource admin + citizen-visible endpoints.

Public surface:
- GET  /api/resources                 auth required, filterable
- GET  /api/resources/{id}            auth required
- PATCH /api/resources/{id}/availability  admin only
- POST /api/resources/{id}/reset      admin only, resets shelter capacity

Used by:
- Admin dashboard (list with filters, toggle availability)
- Live map (list available resources for the markers layer)
- Demo reset button (mark all available again)
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.db import get_database
from app.models import resource as resource_model
from app.routes.deps import get_current_user, require_db
from app.schemas.resource import (
    RESOURCE_TYPES,
    ResourceAvailabilityUpdate,
    ResourceListOut,
    ResourceOut,
)
from app.services import resource as resource_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["resources"])


def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"success": False, "error": "Admin role required"},
        )


@router.get("/resources", response_model=ResourceListOut)
async def list_resources(
    type: Optional[str] = Query(default=None),
    assistance: Optional[str] = Query(default=None),
    available_only: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0, le=100000),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> ResourceListOut:
    """List resources with optional filters.

    - Citizens see available_only=true by default? No — they see all so
      they understand the system. Admins see all too. Filters are explicit.

    Returns `total` (full match count) + `offset` + `limit` so the
    dashboard can paginate cleanly.
    """
    # Reject bad `?type=` early — saves a DB roundtrip on typos.
    if type is not None and type not in RESOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "success": False,
                "error": f"type must be one of {RESOURCE_TYPES}",
                "got": type,
            },
        )

    items, total = await resource_service.list_resources(
        type_=type,
        available_only=available_only,
        assistance=assistance,
        limit=limit,
        offset=offset,
    )
    return ResourceListOut(
        items=[ResourceOut(**i) for i in items],
        count=len(items),
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/resources/{resource_id}", response_model=ResourceOut)
async def get_resource(
    resource_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> ResourceOut:
    item = await resource_service.get_resource(resource_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Resource not found"},
        )
    return ResourceOut(**item)


@router.patch("/resources/{resource_id}/availability", response_model=ResourceOut)
async def set_availability(
    payload: ResourceAvailabilityUpdate,
    resource_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> ResourceOut:
    """Toggle a resource's availability. Admin only."""
    _require_admin(current_user)
    ok = await resource_service.set_availability(resource_id, payload.available)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "error": "Resource not found or unchanged"},
        )
    item = await resource_service.get_resource(resource_id)
    return ResourceOut(**item)


@router.post("/resources/reset", response_model=ResourceListOut)
async def reset_all_resources(
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(require_db),
) -> ResourceListOut:
    """Admin-only: mark every resource available and zero shelter usage.

    One-click demo reset before presenting.
    """
    _require_admin(current_user)
    db = get_database()
    await db[resource_model.COLLECTION].update_many(
        {},
        {
            "$set": {
                "available": True,
                "capacity_used": 0,
                "updated_at": resource_model._utcnow(),  # noqa: SLF001
            }
        },
    )
    items, _ = await resource_service.list_resources(limit=2000)
    return ResourceListOut(items=[ResourceOut(**i) for i in items], count=len(items))