"""Situation-report service.

Responsibilities:
1. Aggregate incident stats for a time window (cheap — pure Mongo).
2. Call the *cheap* summary model to produce a headline, narrative
   summary, and 3-5 recommendations. Always fall back to a deterministic
   template if the LLM is unavailable — never leave the caller hanging.
3. Persist the result.
4. Render text + PDF exports for sharing.

Pure aggregation lives in `aggregate_window()` so the smoke test can
exercise it without the LLM. The LLM call lives in `generate_sitrep()`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.core.db import get_database
from app.core.openai_client import chat_json, is_configured
from app.models import resource as resource_model
from app.models import report as report_model
from app.models import sitrep as sitrep_model
from app.schemas.report import _filter_assistance_keys

logger = logging.getLogger(__name__)

# Cap how many individual incidents we feed the LLM — keeps tokens cheap.
DEFAULT_MAX_INCIDENTS = 20
# Token ceiling for summary call.
SUMMARY_MAX_TOKENS = 700


# ----------------------------------------------------------------------
# 1. Aggregation
# ----------------------------------------------------------------------
async def aggregate_window(
    *,
    window_hours: int,
    divisions: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], datetime, datetime]:
    """Return (stats, sampled_incidents, window_start, window_end).

    Sampled incidents are the most recent N relevant reports, each shaped
    as the LLM sees them (description, location, severity, urgency, etc.).
    """
    db = get_database()
    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(hours=window_hours)

    base_match: Dict[str, Any] = {"created_at": {"$gte": window_start, "$lte": window_end}}
    if divisions:
        base_match["location.division"] = {"$in": divisions}

    # Counts pipeline
    pipeline = [
        {"$match": base_match},
        {
            "$group": {
                "_id": None,
                "total_incidents": {"$sum": 1},
                "affected_people": {
                    "$sum": {"$ifNull": ["$affected_count", 0]}
                },
                "immediate_danger": {
                    "$sum": {"$cond": [{"$eq": ["$immediate_danger", True]}, 1, 0]}
                },
            }
        },
    ]
    counts: Dict[str, Any] = {
        "total_incidents": 0,
        "affected_people": 0,
        "immediate_danger": 0,
    }
    async for row in db[report_model.COLLECTION].aggregate(pipeline):
        counts.update(row)

    # Severity/type/division/assistance breakdowns — done separately so each
    # can fall back to {} without blocking the whole aggregation.
    async def _facets(field_path: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        pipeline2 = [
            {"$match": base_match},
            {"$group": {"_id": f"${field_path}", "n": {"$sum": 1}}},
        ]
        async for row in db[report_model.COLLECTION].aggregate(pipeline2):
            k = row["_id"]
            if k is None:
                continue
            out[str(k)] = out.get(str(k), 0) + row["n"]
        return out

    by_severity = await _facets("ai_output.combined.severity")
    by_type = await _facets("ai_output.combined.type")
    by_division = await _facets("location.division")

    # Assistance: arrays need $unwind first.
    async def _assistance_facets() -> Dict[str, int]:
        out: Dict[str, int] = {}
        pipeline3 = [
            {"$match": base_match},
            {"$unwind": {"path": "$assistance", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": "$assistance", "n": {"$sum": 1}}},
        ]
        async for row in db[report_model.COLLECTION].aggregate(pipeline3):
            k = _filter_assistance_keys([row["_id"]])[0] if isinstance(row["_id"], str) else None
            if k:
                out[k] = out.get(k, 0) + row["n"]
        return out

    assistance_counts = await _assistance_facets()

    # Resource availability snapshot — separate collection.
    total_resources = await db[resource_model.COLLECTION].count_documents({})
    available_resources = await db[resource_model.COLLECTION].count_documents({"available": True})

    stats = {
        "total_incidents": counts["total_incidents"],
        "affected_people": counts["affected_people"],
        "by_severity": by_severity or {"unknown": counts["total_incidents"]},
        "by_type": by_type,
        "by_division": by_division,
        "assistance_counts": assistance_counts,
        "immediate_danger": counts["immediate_danger"],
        "resource_availability": {
            "total": total_resources,
            "available": available_resources,
            "in_use": total_resources - available_resources,
        },
    }

    # Sample the most recent incidents for the LLM (cap at max_incidents).
    sample_pipeline = [
        {"$match": base_match},
        {"$sort": {"created_at": -1}},
        {"$limit": DEFAULT_MAX_INCIDENTS},
    ]
    sampled: List[Dict[str, Any]] = []
    incident_ids: List[str] = []
    async for doc in db[report_model.COLLECTION].aggregate(sample_pipeline):
        ai = (doc.get("ai_output") or {}).get("combined") or {}
        loc = doc.get("location") or {}
        coords = loc.get("coords") or {}
        sampled.append(
            {
                "id": str(doc["_id"]),
                "division": loc.get("division"),
                "district": loc.get("district"),
                "upazila": loc.get("upazila"),
                "area": loc.get("area"),
                "lat": coords.get("lat"),
                "lng": coords.get("lng"),
                "severity": ai.get("severity") or "medium",
                "type": ai.get("type") or "other",
                "urgency_score": ai.get("urgency_score", 50),
                "affected_count": doc.get("affected_count"),
                "assistance": _filter_assistance_keys(doc.get("assistance") or []),
                "immediate_danger": bool(doc.get("immediate_danger", False)),
                "summary": (ai.get("summary") or "")[:200],
            }
        )
        incident_ids.append(str(doc["_id"]))

    return stats, sampled, window_start, window_end


# ----------------------------------------------------------------------
# 2. LLM call
# ----------------------------------------------------------------------
SUMMARY_SYSTEM_PROMPT = """You are a senior disaster-response analyst for Bangladesh.
You will receive a JSON snapshot of incidents collected over a time window,
plus aggregated stats. Produce a brief situation report.

Return ONLY a JSON object with these fields:
{
  "headline": "<= 80 chars, punchy single-line summary>",
  "summary": "<= 3 sentences, plain English, neutral tone>",
  "recommendations": ["3-5 short imperative actions, e.g. 'Pre-position rescue boats in Kurigram.'"]
}

Rules:
- Be specific: name divisions, severity counts, resource gaps.
- Highlight any 'critical' incidents by area and any 'water' assistance if floods dominate.
- Note if affected_count is large vs shelter capacity.
- Recommendations must be actionable by responders, not generic platitudes.
- Do NOT invent numbers; only quote ones from the input.
"""

SUMMARY_USER_TEMPLATE = """Stats ({window_hours}h window):
{stats}

Sampled incidents ({n} of {total}):
{incidents_json}

Return strict JSON."""


async def _call_summary_llm(
    stats: Dict[str, Any],
    sampled: List[Dict[str, Any]],
    window_hours: int,
) -> Tuple[Dict[str, Any], str, str]:
    """Call the cheap model. Returns (parsed, status, model_name).

    `status` is "ok" on success, "fallback" on error — never raises.
    """
    settings = get_settings()
    model_name = settings.openai_summary_model or settings.openai_text_model
    if not is_configured():
        return {}, "fallback", model_name

    incidents_json = "[\n" + ",\n".join(
        "{"
        f'"id":"{(s.get("id") or "")[:8]}…",'
        f'"div":"{s.get("division") or ""}",'
        f'"sev":"{s.get("severity") or "medium"}",'
        f'"type":"{s.get("type") or "other"}",'
        f'"urg":{int(s.get("urgency_score") or 0)},'
        f'"affected":{int(s.get("affected_count") or 0)},'
        f'"assist":{s.get("assistance") or []},'
        f'"danger":{str(bool(s.get("immediate_danger"))).lower()},'
        f'"summary":"{(s.get("summary") or "").replace(chr(34), chr(39))[:120]}"'
        "}"
        for s in sampled
    ) + "\n]"

    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": SUMMARY_USER_TEMPLATE.format(
                window_hours=window_hours,
                stats=_shorten_for_prompt(stats),
                n=len(sampled),
                total=stats.get("total_incidents", len(sampled)),
                incidents_json=incidents_json,
            ),
        },
    ]
    try:
        parsed = await chat_json(
            model=model_name,
            messages=messages,
            max_tokens=SUMMARY_MAX_TOKENS,
            temperature=0.3,
        )
        # Light validation
        parsed.setdefault("headline", "")
        parsed.setdefault("summary", "")
        recs = parsed.get("recommendations") or []
        if not isinstance(recs, list):
            recs = []
        parsed["recommendations"] = [str(x)[:200] for x in recs[:6]]
        return parsed, "ok", model_name
    except Exception as exc:  # noqa: BLE001
        logger.warning("Summary LLM call failed (%s); using fallback.", exc)
        return {}, "fallback", model_name


def _shorten_for_prompt(stats: Dict[str, Any]) -> str:
    """Compact the stats dict so we don't burn prompt budget on whitespace."""
    import json
    return json.dumps(stats, separators=(",", ":"))[:1800]


def _fallback_sitrep(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic headline/summary/recommendations when no LLM is available."""
    sev = stats.get("by_severity") or {}
    crit = int(sev.get("critical", 0))
    high = int(sev.get("high", 0))
    total = int(stats.get("total_incidents", 0))
    affected = int(stats.get("affected_people", 0))
    top_division = ""
    by_div = stats.get("by_division") or {}
    if by_div:
        top_division = max(by_div.items(), key=lambda kv: kv[1])[0]
    top_assistance = ""
    by_assist = stats.get("assistance_counts") or {}
    if by_assist:
        top_assistance = max(by_assist.items(), key=lambda kv: kv[1])[0]

    if crit and top_division:
        headline = f"{crit} critical incident{'s' if crit != 1 else ''} in {top_division}"
    elif total:
        headline = f"{total} incidents reported in the last window"
    else:
        headline = "No active incidents in window"

    parts = []
    if total:
        parts.append(
            f"{total} incident{'s' if total != 1 else ''} reported, "
            f"{crit} critical and {high} high severity."
        )
    if affected:
        parts.append(f"Approximately {affected} people affected.")
    if top_assistance:
        parts.append(f"Top assistance needed: {top_assistance}.")
    ra = stats.get("resource_availability") or {}
    if ra.get("in_use"):
        parts.append(f"{ra['in_use']} of {ra['total']} resources currently deployed.")
    summary = " ".join(parts) or "No data available for this window."

    recs: List[str] = []
    if crit:
        recs.append(f"Dispatch nearest {top_assistance or 'rescue'} units to {top_division} immediately.")
    if high:
        recs.append("Confirm standby with high-severity area commanders within 15 minutes.")
    ra = stats.get("resource_availability") or {}
    if ra.get("in_use", 0) > 0:
        recs.append("Track in-use resources and pre-position replacements for next wave.")
    if not recs:
        recs.append("Continue passive monitoring; reassess in one hour.")
    return {"headline": headline[:120], "summary": summary, "recommendations": recs[:5]}


# ----------------------------------------------------------------------
# 3. Public entry points
# ----------------------------------------------------------------------
async def generate_sitrep(
    *,
    window_hours: int,
    divisions: Optional[List[str]] = None,
    max_incidents: int = DEFAULT_MAX_INCIDENTS,
    trigger: str = "manual",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate + persist a new sitrep. Always returns a doc."""
    stats, sampled, window_start, window_end = await aggregate_window(
        window_hours=window_hours, divisions=divisions
    )
    sampled = sampled[:max_incidents]

    parsed, status, model_name = await _call_summary_llm(stats, sampled, window_hours)
    if status == "fallback" or not parsed:
        parsed = _fallback_sitrep(stats)

    doc = await sitrep_model.create_sitrep(
        {
            "window_start": window_start,
            "window_end": window_end,
            "scope": {"divisions": divisions or [], "bbox": None},
            "stats": stats,
            "headline": str(parsed.get("headline") or "").strip()[:160],
            "summary": str(parsed.get("summary") or "").strip(),
            "recommendations": list(parsed.get("recommendations") or []),
            "incidents_sampled": len(sampled),
            "incident_ids": [s["id"] for s in sampled],
            "model": model_name,
            "model_status": status,
            "generated_at": datetime.now(timezone.utc),
            "trigger": trigger,
            "generated_by": user_id or "system",
        }
    )
    return doc


async def latest_sitrep(divisions: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    return await sitrep_model.find_latest(scope_divisions=divisions)


async def list_sitreps(limit: int = 10, divisions: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    return await sitrep_model.find_recent(limit=limit, scope_divisions=divisions)


async def get_sitrep(sitrep_id: str) -> Optional[Dict[str, Any]]:
    return await sitrep_model.find_by_id(sitrep_id)


# ----------------------------------------------------------------------
# 4. Exports (text + PDF)
# ----------------------------------------------------------------------
def render_text(sitrep: Dict[str, Any]) -> str:
    """Plain-text rendering suitable for pasting into a chat / SMS."""
    stats = sitrep.get("stats", {}) or {}
    sev = stats.get("by_severity") or {}
    ra = stats.get("resource_availability") or {}

    lines: List[str] = []
    lines.append("=== SITUATION REPORT ===")
    lines.append(f"Generated: {sitrep.get('generated_at')}")
    lines.append(
        f"Window: {sitrep.get('window_start')} → {sitrep.get('window_end')} "
        f"({sitrep.get('scope', {}).get('divisions') or 'all divisions'})"
    )
    lines.append("")
    lines.append(sitrep.get("headline") or "No headline.")
    lines.append("")
    lines.append("Summary:")
    lines.append(sitrep.get("summary") or "—")
    lines.append("")
    lines.append("Stats:")
    lines.append(f"  Total incidents : {stats.get('total_incidents', 0)}")
    lines.append(f"  By severity     : " + ", ".join(f"{k}={v}" for k, v in sorted(sev.items())))
    lines.append(f"  Affected people : {stats.get('affected_people', 0)}")
    if ra:
        lines.append(
            f"  Resources       : {ra.get('available', 0)} available / "
            f"{ra.get('in_use', 0)} in use / {ra.get('total', 0)} total"
        )
    recs = sitrep.get("recommendations") or []
    if recs:
        lines.append("")
        lines.append("Recommended actions:")
        for r in recs:
            lines.append(f"  • {r}")
    lines.append("")
    lines.append(f"Incidents sampled: {sitrep.get('incidents_sampled', 0)}")
    lines.append(f"Model: {sitrep.get('model')} ({sitrep.get('model_status')})")
    return "\n".join(lines)


def render_pdf(sitrep: Dict[str, Any]) -> bytes:
    """Render a PDF. Falls back to plain text wrapped as PDF bytes if
    reportlab isn't installed (keeps the endpoint functional in any env).
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )
        from io import BytesIO

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, title=sitrep.get("headline") or "Situation Report")
        styles = getSampleStyleSheet()
        flow = []
        flow.append(Paragraph("Situation Report", styles["Title"]))
        flow.append(Spacer(1, 8))
        flow.append(Paragraph(sitrep.get("headline") or "", styles["Heading2"]))
        flow.append(
            Paragraph(
                f"Window: {sitrep.get('window_start')} → {sitrep.get('window_end')}",
                styles["Normal"],
            )
        )
        flow.append(Spacer(1, 8))
        flow.append(Paragraph("Summary", styles["Heading3"]))
        flow.append(Paragraph(sitrep.get("summary") or "—", styles["Normal"]))
        flow.append(Spacer(1, 8))
        stats = sitrep.get("stats", {}) or {}
        flow.append(Paragraph("Stats", styles["Heading3"]))
        flow.append(
            Paragraph(
                f"Total incidents: {stats.get('total_incidents', 0)}<br/>"
                f"By severity: {stats.get('by_severity')}<br/>"
                f"Affected people: {stats.get('affected_people', 0)}<br/>"
                f"Resources: {stats.get('resource_availability')}",
                styles["Normal"],
            )
        )
        recs = sitrep.get("recommendations") or []
        if recs:
            flow.append(Spacer(1, 8))
            flow.append(Paragraph("Recommended actions", styles["Heading3"]))
            for r in recs:
                flow.append(Paragraph(f"• {r}", styles["Normal"]))
        doc.build(flow)
        return buf.getvalue()
    except ImportError:
        # Fallback: a minimal PDF that just contains the text body.
        # Done as raw bytes so the endpoint never 500s because of a missing
        # optional dependency.
        return _minimal_text_pdf(render_text(sitrep))


def _minimal_text_pdf(body: str) -> bytes:
    """Tiny hand-rolled PDF containing just the text rendering."""
    sanitized = body.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content_stream = f"BT /F1 11 Tf 50 760 Td ({sanitized}) Tj ET".encode("latin-1", errors="replace")
    objects: List[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
    )
    objects.append(b"<< /Length " + str(len(content_stream)).encode() + b" >>\nstream\n" + content_stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets: List[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode()
    return bytes(out)