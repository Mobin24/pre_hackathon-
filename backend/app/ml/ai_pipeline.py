"""AI pipeline for citizen incident reports.

Three stages:
1. `run_text_ai`  — cheap text-only model extracts structured insights
2. `run_image_ai` — moderate vision model reads each uploaded image
3. `combine`      — merges the two with a deterministic heuristic so we
                     don't spend a third API call in the common case.

Every stage degrades gracefully:
- Text failure    → fallback dict (severity=medium, urgency=50)
- Image failure   → `ImageInsights(has_image=False)`
- Combine failure → uses the text result verbatim

All model identifiers come from `Settings` so they can be swapped per env.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.openai_client import chat_json, is_configured
from app.schemas.report import _filter_assistance_keys
from app.services import storage

logger = logging.getLogger(__name__)

# --- Limits ----------------------------------------------------------------
MAX_IMAGE_BYTES_FOR_VISION = 4 * 1024 * 1024  # 4 MB per image cap for the API call
VISION_MAX_IMAGES = 3                         # never send more than 3 to vision
IMAGE_MIME_TO_OPENAI_TAG = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}


def _project_assistance(values: Any) -> List[str]:
    """Defensive projection onto the closed AssistanceType vocabulary.

    Used after every AI stage to guarantee the stored list never contains
    a key the frontend cannot render.
    """
    return _filter_assistance_keys(values or [])

# --- Prompts ---------------------------------------------------------------
TEXT_SYSTEM_PROMPT = """You are a disaster-response triage analyst for Bangladesh.
Given a citizen's free-text incident report, extract structured JSON.

Return ONLY a JSON object with these fields:
{
  "type": one of ["flood","cyclone","fire","earthquake","landslide","storm","tornado","drought","medical","other"],
  "severity": one of ["low","medium","high","critical"],
  "urgency_score": integer 0-100, where 100 = life-threatening right now,
  "assistance_detected": array of strings drawn from ["rescue_team","food","water","medical","shelter","medicine","ambulance","rescue_boat","baby_supplies","clothes","other"],
  "summary": 1-2 sentence neutral rephrasing of the situation in English,
  "confidence": 0-1 your confidence in the call,
  "language": ISO code of the report's primary language,
  "raw_signal": { "keywords": [string], "tone": "panic|urgent|calm|neutral" }
}

Rules:
- Be conservative on `severity` — only mark `critical` if the text clearly indicates imminent life threat.
- If the text is ambiguous, prefer `other` and `medium`.
- Do NOT invent facts not present in the text.
- For `assistance_detected`: ONLY emit keys from the exact list above. If none applies, output []. Never invent new keys (e.g. "rescue helicopter", "psychological first aid").
"""

TEXT_USER_TEMPLATE = """Citizen location: {location}
Affected people count: {affected_count}
Assistance requested by user: {assistance}
Immediate danger flag: {immediate_danger}
Incident time: {incident_time}

Citizen report:
\"\"\"
{text}
\"\"\"

Respond with the JSON object only."""


VISION_SYSTEM_PROMPT = """You analyze disaster-scene photos for a Bangladesh relief platform.
Return ONLY a JSON object with these fields:
{
  "has_image": true,
  "caption": 1 sentence factual description of what is visible,
  "type_hint": one of ["flood","cyclone","fire","earthquake","landslide","storm","tornado","drought","medical","other"],
  "severity_hint": one of ["low","medium","high","critical"],
  "urgency_hint": integer 0-100,
  "safety_flag": one of ["none","smoke","fire","flood_water","damage","structural_collapse","medical"],
  "confidence": 0-1
}

Do not speculate beyond what is visible in the image. If unclear, use type_hint="other", severity_hint="medium"."""

COMBINE_SYSTEM_PROMPT = """You are a senior dispatcher. Combine the text analysis and the image
analysis (when present) into a single final triage JSON.

Return ONLY a JSON object with these fields:
{
  "type": one of ["flood","cyclone","fire","earthquake","landslide","storm","tornado","drought","medical","other"],
  "severity": one of ["low","medium","high","critical"],
  "urgency_score": integer 0-100,
  "summary": 2-3 sentence operational summary a dispatcher can act on,
  "recommendation": 1-2 sentence concrete next step,
  "assistance_needed": array of strings drawn from ["rescue_team","food","water","medical","shelter","medicine","ambulance","rescue_boat","baby_supplies","clothes","other"],
  "confidence": 0-1
}

Rules:
- If image severity_hint is higher than text severity, lean toward the higher of the two.
- The `recommendation` MUST be actionable (deploy X, dispatch Y, monitor Z).
- Do not mention AI or models.
- For `assistance_needed`: ONLY emit keys from the exact list above. If none applies, output []. Never invent new keys."""


# --- Helpers ---------------------------------------------------------------
def _fallback_text(reason: str) -> Dict[str, Any]:
    return {
        "type": "other",
        "severity": "medium",
        "urgency_score": 50,
        "assistance_detected": [],
        "summary": "",
        "confidence": 0.0,
        "language": "unknown",
        "raw_signal": {"error": reason},
    }


def _fallback_image(reason: str) -> Dict[str, Any]:
    return {
        "has_image": False,
        "caption": "",
        "type_hint": "other",
        "severity_hint": "medium",
        "urgency_hint": 50,
        "safety_flag": "none",
        "confidence": 0.0,
        "error": reason,
    }


def _fallback_combined(reason: str) -> Dict[str, Any]:
    return {
        "type": "other",
        "severity": "medium",
        "urgency_score": 50,
        "summary": "",
        "recommendation": "Manual review required.",
        "assistance_needed": [],
        "confidence": 0.0,
        "error": reason,
    }


def _location_str(location: Dict[str, Any]) -> str:
    parts = [
        location.get("area"),
        location.get("upazila"),
        location.get("district"),
        location.get("division"),
    ]
    return ", ".join(p for p in parts if p) or "unspecified"


def _build_text_messages(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = (payload.get("description") or "").strip()
    return [
        {"role": "system", "content": TEXT_SYSTEM_PROMPT},
        {"role": "user", "content": TEXT_USER_TEMPLATE.format(
            text=text,
            location=_location_str(payload.get("location") or {}),
            affected_count=payload.get("affected_count") or "unspecified",
            assistance=", ".join(payload.get("assistance") or []) or "none specified",
            immediate_danger="yes" if payload.get("immediate_danger") else "no",
            incident_time=payload.get("incident_time") or "unspecified",
        )},
    ]


def _build_image_content(images_b64: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Build the multi-modal content array for the vision model."""
    content: List[Dict[str, Any]] = [{"type": "text", "text": (
        "Analyze these incident photo(s) and return the required JSON."
    )}]
    for img in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{img['mime']};base64,{img['data']}",
            },
        })
    return content


def _encode_local_images(images: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Read image files from disk and base64-encode them for vision."""
    encoded: List[Dict[str, str]] = []
    for img in images[:VISION_MAX_IMAGES]:
        try:
            path = storage.resolve_upload_path(img["filename"])
        except ValueError:
            continue
        if not path.exists():
            continue
        try:
            size = path.stat().st_size
            if size > MAX_IMAGE_BYTES_FOR_VISION:
                logger.info("Skipping oversize image %s (%s bytes)", img["filename"], size)
                continue
            mime = (img.get("content_type") or "image/jpeg").lower()
            if mime not in IMAGE_MIME_TO_OPENAI_TAG:
                continue
            with open(path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
            encoded.append({"mime": mime, "data": b64, "filename": img["filename"]})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to encode %s: %s", img.get("filename"), exc)
    return encoded


# --- Stage 1: text ----------------------------------------------------------
async def run_text_ai(payload: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_settings()
    if not is_configured():
        return _fallback_text("OPENAI_API_KEY not set")
    if not (payload.get("description") or "").strip():
        return _fallback_text("empty description")
    try:
        return await chat_json(
            model=settings.openai_text_model,
            messages=_build_text_messages(payload),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("text AI failed")
        return _fallback_text(str(exc))


# --- Stage 2: image ---------------------------------------------------------
async def run_image_ai(images: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not images:
        return {"has_image": False, "caption": "", "type_hint": "other",
                "severity_hint": "medium", "urgency_hint": 50,
                "safety_flag": "none", "confidence": 0.0}
    settings = get_settings()
    if not is_configured():
        return _fallback_image("OPENAI_API_KEY not set")

    encoded = _encode_local_images(images)
    if not encoded:
        return _fallback_image("no readable images")

    try:
        client_messages = [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {"role": "user", "content": _build_image_content(encoded)},
        ]
        return await chat_json(
            model=settings.openai_vision_model,
            messages=client_messages,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("vision AI failed")
        return _fallback_image(str(exc))


# --- Stage 3: combine -------------------------------------------------------
async def combine(
    text_out: Dict[str, Any],
    image_out: Optional[Dict[str, Any]],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge text + image insights into a single triage JSON.

    Strategy:
    - If image has has_image=False (or missing/error), return a deterministic
      copy of `text_out` with a recommendation filled in locally.
    - Otherwise, ask the text model to do the final synthesis — cheaper than
      another vision call.
    """
    settings = get_settings()
    has_image = bool(image_out and image_out.get("has_image"))

    # Simple deterministic fallback if image is absent or AI is off.
    if not has_image or not is_configured():
        out = dict(text_out)
        out["recommendation"] = _local_recommendation(text_out, payload)
        out["assistance_needed"] = _project_assistance(
            text_out.get("assistance_detected")
        )
        out.setdefault("confidence", text_out.get("confidence", 0.5))
        return out

    try:
        merged = await chat_json(
            model=settings.openai_text_model,  # use cheap model for synthesis
            messages=[
                {"role": "system", "content": COMBINE_SYSTEM_PROMPT},
                {"role": "user", "content": (
                    "TEXT_ANALYSIS:\n" + _safe_json(text_out) +
                    "\n\nIMAGE_ANALYSIS:\n" + _safe_json(image_out) +
                    "\n\nLOCATION: " + _location_str(payload.get("location") or {}) +
                    "\nASSISTANCE_REQUESTED_BY_USER: " +
                    ", ".join(payload.get("assistance") or []) +
                    "\n\nReturn the final combined JSON."
                )},
            ],
            max_tokens=500,
            temperature=0.2,
        )
        # Project through the closed enum so the dashboard always renders.
        merged["assistance_needed"] = _project_assistance(
            merged.get("assistance_needed")
        )
        return merged
    except Exception as exc:  # noqa: BLE001
        logger.exception("combine AI failed; falling back to text output")
        out = dict(text_out)
        out["recommendation"] = _local_recommendation(text_out, payload)
        out["assistance_needed"] = _project_assistance(
            text_out.get("assistance_detected")
        )
        out["error"] = str(exc)
        return out


def _local_recommendation(text_out: Dict[str, Any], payload: Dict[str, Any]) -> str:
    severity = text_out.get("severity", "medium")
    score = int(text_out.get("urgency_score", 50))
    assists = text_out.get("assistance_detected") or []
    assists = assists or payload.get("assistance") or []
    if severity == "critical" or score >= 80:
        return (
            f"Dispatch rescue team immediately. Send {', '.join(assists) or 'triage supplies'}."
        )
    if severity == "high" or score >= 60:
        return f"Send {', '.join(assists) or 'assessment team'} within the hour."
    if severity == "medium":
        return "Monitor the area; stage supplies nearby."
    return "Log the report and continue observation."


def _safe_json(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(obj)


# --- Top-level entry --------------------------------------------------------
async def process_report(report_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full text + image + combine pipeline for one report doc.

    Returns the dict to persist as `ai_output`. Never raises — always
    returns something the route can store.
    """
    settings = get_settings()
    payload = {
        "description": report_doc.get("description", ""),
        "location": report_doc.get("location") or {},
        "affected_count": report_doc.get("affected_count"),
        "assistance": report_doc.get("assistance") or [],
        "immediate_danger": report_doc.get("immediate_danger", False),
        "incident_time": report_doc.get("incident_time"),
        "notes": report_doc.get("notes"),
    }
    images = report_doc.get("images") or []

    # Run text + image in parallel — they're independent.
    text_task = asyncio.create_task(run_text_ai(payload))
    image_task = asyncio.create_task(run_image_ai(images))
    text_out, image_out = await asyncio.gather(text_task, image_task)

    combined = await combine(text_out, image_out, payload)

    return {
        "combined": combined,
        "text": text_out,
        "image": image_out,
        "models": {
            "text": settings.openai_text_model,
            "vision": settings.openai_vision_model if images else None,
        },
    }