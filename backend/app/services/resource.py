"""Thin service layer over the resources Mongo collection.

The matching engine in `app/services/matching.py` is pure and operates on
dicts. This module pulls raw resources out of Mongo, hands them to the
matcher, and assembles the final response shape that the route returns.

Kept tiny on purpose — no caching, no orchestration. If we ever need
caching, do it here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models import resource as resource_model
from app.models import report as report_model
from app.services import matching


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def list_resources(
    *,
    type_: Optional[str] = None,
    available_only: bool = False,
    assistance: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[List[Dict[str, Any]], int]:
    """Returns `(items, total)` where `total` is the full match count.

    Items are already offset/limit sliced. The route layer needs total
    for pagination metadata.
    """
    return await resource_model.find_all(
        type_=type_,
        available_only=available_only,
        assistance=assistance,
        limit=limit,
        offset=offset,
    )


async def get_resource(resource_id: str) -> Optional[Dict[str, Any]]:
    return await resource_model.find_by_id(resource_id)


async def set_availability(resource_id: str, available: bool) -> bool:
    return await resource_model.update_availability(resource_id, available)


async def adjust_shelter_usage(resource_id: str, capacity_used: int) -> bool:
    return await resource_model.update_capacity(resource_id, capacity_used)


async def match_for_report(
    report_id: str,
    *,
    radius_km: float = matching.DEFAULT_RADIUS_KM,
    top_n: int = 3,
) -> Dict[str, Any]:
    """Build the full match response for a stored report.

    Combines:
      - report's location + raw `assistance` keys (from form)
      - AI severity + urgency (if processed)
      - all available resources from Mongo
    """
    report = await report_model.find_raw_by_id(report_id)
    if not report:
        raise LookupError(f"Report {report_id} not found")

    loc = (report.get("location") or {}).get("coords") or {}
    inc_lat = loc.get("lat")
    inc_lng = loc.get("lng")
    if not isinstance(inc_lat, (int, float)) or not isinstance(inc_lng, (int, float)):
        raise ValueError("Report has no coordinates — cannot match by proximity")

    # Severity: prefer AI output, fall back to a reasonable default.
    ai = (report.get("ai_output") or {}).get("combined") or {}
    severity = ai.get("severity") or "medium"
    incident_type = ai.get("type") or report.get("assistance") and "other"

    requested = list(report.get("assistance") or [])
    if not requested:
        # Fall back to AI-inferred needs if the form didn't list any.
        requested = list(ai.get("assistance_needed") or [])

    incident: Dict[str, Any] = {
        "lat": float(inc_lat),
        "lng": float(inc_lng),
        "severity": severity,
        "type": incident_type or "other",
        "assistance": requested,
        "affected_count": report.get("affected_count") or 1,
        "units_needed": 1,
        "immediate_danger": bool(report.get("immediate_danger", False)),
    }

    # Pull every available resource. In production we'd filter by bbox here.
    resources, _ = await resource_model.find_all(available_only=True, limit=2000)

    categories = matching.match_for_incident(
        resources,
        incident,
        requested_assistance=requested,
        radius_km=radius_km,
        top_n=top_n,
    )
    actions = matching.suggest_actions(incident, categories, radius_km)

    return {
        "report_id": report_id,
        "incident_severity": severity,
        "incident_type": incident_type or "other",
        "requested_assistance": requested,
        "radius_km": radius_km,
        "categories": categories,
        "suggested_actions": actions,
        "generated_at": _utcnow_iso(),
    }