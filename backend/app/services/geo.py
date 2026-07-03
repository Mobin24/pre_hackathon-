"""Geo-intelligence services.

Currently exposes one helper:

    detect_hotspots(reports, grid, min_count, top_n)

The algorithm is intentionally simple — pure-Python grid bucketing over a
recent window of reports. It runs in milliseconds at hackathon scale
(500–2000 reports) and requires zero new dependencies. See
`docs/geo-flow.md` §3 for the rationale.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Severity ordering used for the `severity_score` ranking.
# Higher number = more severe = more important for triage.
SEVERITY_WEIGHT = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

# Type returned by combined AI output when nothing matches.
_FALLBACK_TYPE = "other"


def _cell_id(lat: float, lng: float, grid: float) -> str:
    """Snap (lat, lng) to a grid cell and return the string key.

    Example (grid=0.05): lat=24.847, lng=91.412 → "24.85_91.40"
    """
    clat = round(lat / grid) * grid
    clng = round(lng / grid) * grid
    # Use a stable repr so we never round-trip through float formatting.
    return f"{clat:.4f}_{clng:.4f}"


def _cell_center(lat: float, lng: float, grid: float) -> Dict[str, float]:
    """Return the (lat, lng) of a cell's center given any point inside it."""
    return {
        "lat": round(lat / grid) * grid,
        "lng": round(lng / grid) * grid,
    }


def _read_combined(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pull `combined` out of a raw report doc; tolerate None / missing."""
    ai = doc.get("ai_output")
    if not isinstance(ai, dict):
        return None
    combined = ai.get("combined")
    if not isinstance(combined, dict):
        return None
    return combined


def _severity_score(severity: str, count: int) -> int:
    """Higher = more dangerous. Combines severity with volume."""
    return SEVERITY_WEIGHT.get(severity, 1) * count


def detect_hotspots(
    reports: List[Dict[str, Any]],
    *,
    grid: float = 0.05,
    min_count: int = 3,
    top_n: int = 20,
) -> List[Dict[str, Any]]:
    """Group `reports` into ~5km grid cells and score the dense ones.

    Parameters
    ----------
    reports : list of raw Mongo docs (each MUST have `location.coords`
              and ideally `ai_output.combined`).
    grid    : cell size in degrees. 0.05 ≈ 5.5 km. Must be > 0.
    min_count : minimum reports in a cell to qualify as a hotspot.
    top_n   : cap the returned list.

    Returns a list of hotspot dicts sorted by `severity_score` desc:
        {
          "cell": {"lat": ..., "lng": ..., "radius_km": ~5.5},
          "count": int,
          "avg_severity": "critical" | "high" | "medium" | "low",
          "max_urgency": int (0-100),
          "top_type": "flood" | ...,
          "report_ids": [str, ...],
          "severity_score": int,
        }
    """
    if grid <= 0:
        raise ValueError("grid must be positive")
    if min_count < 1:
        raise ValueError("min_count must be >= 1")

    # Bucket reports by cell.
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for doc in reports:
        coords = (doc.get("location") or {}).get("coords") or {}
        lat, lng = coords.get("lat"), coords.get("lng")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            continue
        buckets[_cell_id(lat, lng, grid)].append(doc)

    hotspots: List[Dict[str, Any]] = []
    for cell_key, cell_reports in buckets.items():
        if len(cell_reports) < min_count:
            continue

        # Pull signals from each report's AI combined output if available,
        # otherwise fall back to conservative defaults.
        severities: List[str] = []
        urgencies: List[int] = []
        types: List[str] = []
        ids: List[str] = []
        for r in cell_reports:
            combined = _read_combined(r)
            sev = (combined or {}).get("severity") or "medium"
            urg = (combined or {}).get("urgency_score")
            typ = (combined or {}).get("type") or _FALLBACK_TYPE
            severities.append(sev if sev in SEVERITY_WEIGHT else "medium")
            urgencies.append(int(urg) if isinstance(urg, (int, float)) else 50)
            types.append(typ)
            ids.append(str(r.get("_id")))

        # The cell's "avg_severity" = the worst severity present (most urgent).
        worst_sev = max(severities, key=lambda s: SEVERITY_WEIGHT.get(s, 1))
        most_common_type = Counter(types).most_common(1)[0][0]

        # Cell center is the first report's snapped cell (all reports in the
        # bucket share the same cell center by construction).
        first = cell_reports[0]
        fcoords = (first.get("location") or {}).get("coords") or {}
        center = _cell_center(float(fcoords["lat"]), float(fcoords["lng"]), grid)

        hotspots.append(
            {
                "cell": {
                    "lat": center["lat"],
                    "lng": center["lng"],
                    # Rough radius for the rendered circle. 1° ≈ 111 km.
                    "radius_km": round(grid * 111.0 / 2.0, 2),
                },
                "count": len(cell_reports),
                "avg_severity": worst_sev,
                "max_urgency": max(urgencies),
                "top_type": most_common_type,
                "report_ids": ids,
                "severity_score": _severity_score(worst_sev, len(cell_reports)),
            }
        )

    hotspots.sort(key=lambda h: h["severity_score"], reverse=True)
    return hotspots[:top_n]


def build_hotspots_response(
    hotspots: List[Dict[str, Any]],
    *,
    window_hours: int,
    generated_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Wrap hotspots into the public JSON envelope."""
    return {
        "hotspots": hotspots,
        "window_hours": window_hours,
        "count": len(hotspots),
        "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
    }