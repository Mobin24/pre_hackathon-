"""Pydantic schemas for citizen incident reports.

Mirrors the payload produced by `frontend/src/user/components/ReportForm.jsx`.
We accept the data as JSON fields via multipart form-data (one field per key),
plus one or more `images` file parts. AI processing is intentionally absent
here — that layer is plugged in by `app/services/report.py` later.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# --- Enums (mirror frontend `ReportForm.jsx`) -------------------------------
BD_DIVISIONS: List[str] = [
    "Dhaka", "Chittagong", "Rajshahi", "Khulna",
    "Barisal", "Sylhet", "Rangpur", "Mymensingh",
]

INCIDENT_TIME_KEYS: List[str] = [
    "just_now", "within_1h", "today", "yesterday", "older",
]


class AssistanceType(str, Enum):
    """Closed vocabulary shared with the frontend `ReportForm.jsx`.

    Both the citizen's manual selection and the LLM's inferred assistance
    MUST come from this enum — keeps the dashboard renderable without
    ad-hoc labels.
    """
    RESCUE_TEAM = "rescue_team"
    FOOD = "food"
    WATER = "water"
    MEDICAL = "medical"
    SHELTER = "shelter"
    MEDICINE = "medicine"
    AMBULANCE = "ambulance"
    RESCUE_BOAT = "rescue_boat"
    BABY_SUPPLIES = "baby_supplies"
    CLOTHES = "clothes"
    OTHER = "other"


# Back-compat alias used by the existing request validator.
ASSISTANCE_KEYS: List[str] = [a.value for a in AssistanceType]
_ASSISTANCE_SET: set = set(ASSISTANCE_KEYS)


def _filter_assistance_keys(values: List[str]) -> List[str]:
    """Project an arbitrary list of strings to the closed AssistanceType
    vocabulary. Unknown / malformed values are dropped silently.

    De-dupes while preserving order.
    """
    seen: set = set()
    out: List[str] = []
    for key in values or []:
        if not isinstance(key, str):
            continue
        k = key.strip()
        if k and k in _ASSISTANCE_SET and k not in seen:
            seen.add(k)
            out.append(k)
    return out


# --- Nested input shapes ----------------------------------------------------
class Coords(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None


class Location(BaseModel):
    """Location block from the form. `division` is the only required field."""

    division: str = Field(..., min_length=1)
    district: Optional[str] = None
    upazila: Optional[str] = None
    area: Optional[str] = None
    coords: Optional[Coords] = None

    @field_validator("division")
    @classmethod
    def _norm_division(cls, v: str) -> str:
        return v.strip()

    @field_validator("district", "upazila", "area")
    @classmethod
    def _norm_optional_str(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


# --- Request ----------------------------------------------------------------
class ReportSubmitRequest(BaseModel):
    """JSON payload sent alongside multipart `images`.

    The frontend posts the form as multipart/form-data with one part per
    primitive field; FastAPI's `Form(...)` reconstructs this object.
    """

    description: str = Field(..., min_length=10, max_length=4000)
    location: Location
    affected_count: Optional[int] = Field(default=None, ge=0)
    assistance: List[str] = Field(default_factory=list)
    immediate_danger: bool = False
    incident_time: Optional[str] = None  # one of INCIDENT_TIME_KEYS or ""
    notes: Optional[str] = Field(default=None, max_length=2000)
    submitted_at: Optional[str] = None  # client clock — audit only

    @field_validator("description")
    @classmethod
    def _strip_description(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("description must be at least 10 characters after trim")
        return v

    @field_validator("assistance")
    @classmethod
    def _clean_assistance(cls, v: List[str]) -> List[str]:
        cleaned = []
        for key in v:
            if not isinstance(key, str):
                continue
            k = key.strip()
            if k and k in ASSISTANCE_KEYS:
                cleaned.append(k)
        # De-dupe while preserving order.
        seen = set()
        return [k for k in cleaned if not (k in seen or seen.add(k))]

    @field_validator("incident_time")
    @classmethod
    def _validate_incident_time(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v = v.strip()
        if v not in INCIDENT_TIME_KEYS:
            raise ValueError(f"incident_time must be one of {INCIDENT_TIME_KEYS}")
        return v

    @field_validator("notes")
    @classmethod
    def _strip_notes(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


# --- Response ---------------------------------------------------------------
class StoredImage(BaseModel):
    filename: str
    url: str
    size: int
    content_type: Optional[str] = None


class ReportLocationOut(BaseModel):
    division: str
    district: Optional[str] = None
    upazila: Optional[str] = None
    area: Optional[str] = None
    coords: Optional[Coords] = None


class ReportOut(BaseModel):
    """Public representation of a stored report. AI fields are nullable."""

    id: str
    user_id: str

    # Raw input
    description: str
    location: ReportLocationOut
    affected_count: Optional[int] = None
    assistance: List[str] = Field(default_factory=list)
    immediate_danger: bool = False
    incident_time: Optional[str] = None
    notes: Optional[str] = None
    images: List[StoredImage] = Field(default_factory=list)

    # Pipeline state — always present, default 'pending_ai'
    status: str = "pending_ai"
    ai_output: Optional[dict] = None
    error: Optional[str] = None

    # Timestamps
    submitted_at_client: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ReportListOut(BaseModel):
    items: List[ReportOut]
    count: int
    total: int = 0
    offset: int = 0
    limit: int = 0


class ReportStatusUpdate(BaseModel):
    """Admin-only status transition request."""
    status: str = Field(..., description="Target status: 'resolved' | 'failed' | 'pending_ai' | 'processed'")
    notes: Optional[str] = Field(default=None, description="Audit note (optional)")

    @field_validator("status")
    @classmethod
    def _allowed(cls, v: str) -> str:
        v = (v or "").strip().lower()
        allowed = {"pending_ai", "processed", "failed", "resolved"}
        if v not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return v


# --- AI output shape -------------------------------------------------------
# Two cheap models run in parallel (text + image). Their outputs are merged
# by a third call into a single `combined` object stored in `ai_output`.
# The intermediate per-model outputs are also retained for explainability.

DISASTER_TYPES: List[str] = [
    "flood", "cyclone", "fire", "earthquake", "landslide",
    "storm", "tornado", "drought", "medical", "other",
]
SEVERITY_LEVELS: List[str] = ["low", "medium", "high", "critical"]


class TextInsights(BaseModel):
    """Output of the cheap text-only model."""
    type: str = Field(default="other")
    severity: str = Field(default="medium")
    urgency_score: int = Field(default=50, ge=0, le=100)
    assistance_detected: List[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=600)
    confidence: float = Field(default=0.5, ge=0, le=1)
    language: str = Field(default="en")
    raw_signal: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("assistance_detected")
    @classmethod
    def _filter_assistance(cls, v: List[str]) -> List[str]:
        """Drop any assistance key that isn't in the closed enum.

        The LLM is instructed to use only `AssistanceType` values; this is
        the safety net that keeps the vocabulary closed.
        """
        return _filter_assistance_keys(v)


class ImageInsights(BaseModel):
    """Output of the moderate vision model."""
    has_image: bool = False
    caption: str = Field(default="", max_length=400)
    type_hint: str = Field(default="other")
    severity_hint: str = Field(default="medium")
    urgency_hint: int = Field(default=50, ge=0, le=100)
    safety_flag: str = Field(default="none")  # none | smoke | fire | flood_water | damage
    confidence: float = Field(default=0.5, ge=0, le=1)


class CombinedInsights(BaseModel):
    """The final, user-facing AI insights (the `ai_output` field)."""
    type: str = Field(default="other")
    severity: str = Field(default="medium")
    urgency_score: int = Field(default=50, ge=0, le=100)
    summary: str = Field(default="", max_length=800)
    recommendation: str = Field(default="", max_length=600)
    # Closed-vocabulary list. LLM output is filtered through the enum
    # so the dashboard never gets a key it can't render.
    assistance_needed: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)

    @field_validator("assistance_needed")
    @classmethod
    def _filter_assistance(cls, v: List[str]) -> List[str]:
        return _filter_assistance_keys(v)


class AIOutput(BaseModel):
    """The full AI pipeline result stored on the report doc.

    `combined` is what the dashboard renders. `text` and `image` are the
    raw per-model outputs, kept for audit and for future re-combination.
    """
    combined: CombinedInsights
    text: Optional[TextInsights] = None
    image: Optional[ImageInsights] = None
    # `vision` may be None when the report had no images.
    models: Dict[str, Optional[str]] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.utcnow())

    @field_validator("combined")
    @classmethod
    def _clamp_combined(cls, v: CombinedInsights) -> CombinedInsights:
        if v.type not in DISASTER_TYPES:
            v.type = "other"
        if v.severity not in SEVERITY_LEVELS:
            v.severity = "medium"
        v.urgency_score = max(0, min(100, int(v.urgency_score)))
        v.confidence = max(0.0, min(1.0, float(v.confidence)))
        return v


# --- Update ReportOut to expose AIOutput shape ----------------------------
# (We keep ai_output as Optional[dict] so existing callers stay compatible;
# the shape is documented in `AIOutput` above.)