"""Pydantic schemas for situation reports."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# --- Request ---------------------------------------------------------------
class SitrepGenerateRequest(BaseModel):
    """On-demand generation request."""
    window_hours: int = Field(default=24, ge=1, le=720)
    divisions: Optional[List[str]] = Field(
        default=None,
        description="Limit scope to these divisions; omit for all",
    )
    max_incidents_to_summarize: int = Field(default=20, ge=1, le=100)
    trigger: str = Field(default="manual")

    @field_validator("divisions")
    @classmethod
    def _norm_divisions(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        seen: List[str] = []
        for raw in v:
            if not isinstance(raw, str):
                continue
            d = raw.strip()
            if d and d not in seen:
                seen.append(d)
        return seen or None


# --- Response --------------------------------------------------------------
class SitrepScope(BaseModel):
    divisions: List[str] = Field(default_factory=list)
    bbox: Optional[Dict[str, float]] = None


class SitrepStats(BaseModel):
    total_incidents: int = 0
    affected_people: int = 0
    by_severity: Dict[str, int] = Field(default_factory=dict)
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_division: Dict[str, int] = Field(default_factory=dict)
    assistance_counts: Dict[str, int] = Field(default_factory=dict)
    immediate_danger: int = 0
    resource_availability: Dict[str, int] = Field(default_factory=dict)


class SitrepOut(BaseModel):
    id: str
    window_start: str
    window_end: str
    scope: SitrepScope = Field(default_factory=SitrepScope)
    stats: SitrepStats = Field(default_factory=SitrepStats)
    headline: str = ""
    summary: str = ""
    recommendations: List[str] = Field(default_factory=list)
    incidents_sampled: int = 0
    incident_ids: List[str] = Field(default_factory=list)
    model: Optional[str] = None
    model_status: str = "unknown"
    generated_at: str
    trigger: str = "manual"
    generated_by: Optional[str] = None


class SitrepListOut(BaseModel):
    items: List[SitrepOut]
    count: int