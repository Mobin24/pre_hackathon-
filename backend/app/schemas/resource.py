"""Pydantic schemas for relief resources.

Mirrors `app/models/resource.py`. Exposed via:
    - GET  /api/resources
    - GET  /api/resources/{id}
    - PATCH /api/resources/{id}/availability   (admin)
"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Mirror the model enum so the API surface is consistent.
RESOURCE_TYPES: List[str] = [
    "volunteer", "ambulance", "rescue_boat", "rescue_team",
    "shelter", "medical_team", "food_depot", "water_point",
    "medicine_store", "clothes_depot", "baby_supplies", "other",
]


# --- Coordinates + Location ------------------------------------------------
class Coords(BaseModel):
    lat: float
    lng: float

    @field_validator("lat")
    @classmethod
    def _v_lat(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError("lat must be between -90 and 90")
        return v

    @field_validator("lng")
    @classmethod
    def _v_lng(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError("lng must be between -180 and 180")
        return v


class ResourceLocationIn(BaseModel):
    division: str = Field(..., min_length=1)
    district: Optional[str] = None
    area: Optional[str] = None
    coords: Coords


class ResourceLocationOut(BaseModel):
    division: Optional[str] = None
    district: Optional[str] = None
    area: Optional[str] = None
    coords: Optional[Coords] = None


class ContactInfo(BaseModel):
    phone: Optional[str] = None
    name: Optional[str] = None


# --- Request: create / update ---------------------------------------------
class ResourceCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    type: str = Field(...)

    @field_validator("type")
    @classmethod
    def _v_type(cls, v: str) -> str:
        if v not in RESOURCE_TYPES:
            raise ValueError(f"type must be one of {RESOURCE_TYPES}")
        return v

    name: str = Field(..., min_length=1, max_length=200)
    assistance: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    location: ResourceLocationIn
    capacity: int = Field(default=1, ge=0, le=10_000)
    capacity_total: Optional[int] = Field(default=None, ge=0)
    capacity_used: Optional[int] = Field(default=None, ge=0)
    available: bool = True
    contact: ContactInfo = Field(default_factory=ContactInfo)
    priority: int = Field(default=0, ge=-100, le=100)
    tags: List[str] = Field(default_factory=list)


class ResourceAvailabilityUpdate(BaseModel):
    available: bool


# --- Response -------------------------------------------------------------
class ResourceOut(BaseModel):
    """Public representation of a stored resource."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    code: Optional[str] = None
    type: str
    name: str
    assistance: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    location: ResourceLocationOut
    capacity: int = 1
    capacity_total: Optional[int] = None
    capacity_used: Optional[int] = None
    available: bool
    contact: ContactInfo = Field(default_factory=ContactInfo)
    priority: int = 0
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ResourceListOut(BaseModel):
    items: List[ResourceOut]
    count: int
    total: int = 0
    offset: int = 0
    limit: int = 0


# --- Match endpoint -------------------------------------------------------
class ScoredResource(BaseModel):
    """A resource with score and distance metadata attached by the matcher."""
    id: str
    code: Optional[str] = None
    type: str
    name: str
    assistance: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    location: ResourceLocationOut
    capacity: int = 1
    capacity_total: Optional[int] = None
    capacity_used: Optional[int] = None
    available: bool
    contact: ContactInfo = Field(default_factory=ContactInfo)
    distance_km: float
    score: float
    reasons: List[str] = Field(default_factory=list)


class MatchCategory(BaseModel):
    matched_assistance: str
    items: List[ScoredResource]


class MatchResult(BaseModel):
    report_id: str
    incident_severity: str
    incident_type: str
    requested_assistance: List[str]
    radius_km: float
    categories: List[MatchCategory]
    suggested_actions: List[str]
    generated_at: str