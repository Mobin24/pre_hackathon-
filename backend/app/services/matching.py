"""Pure scoring engine for relief matching.

No DB imports — takes plain dicts in, returns plain dicts out. This lets
the smoke test exercise the heuristic in isolation, and makes the matcher
trivially reusable for "what-if" calculations.

Pipeline:
    1. prefilter(resources, incident, radius_km)
       — drops unavailable, drops assistance that doesn't overlap
       — drops resources outside the radius using a cheap squared-distance
         test (no trig).
    2. haversine_km(...) — exact spherical distance, only for survivors.
    3. score_resource(r, incident, distance_km) — weighted sum.
    4. rank_by_assistance(candidates, ...) — top-N per requested key.

Time complexity: O(N) where N is total resources. With ~50 resources this
runs in microseconds. The squared-distance prefilter ensures we only pay
for the trig on the ~10–30 survivors.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

# --- Constants -------------------------------------------------------------
SEVERITY_WEIGHT: Dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

# How strongly each factor contributes to the final score. Tuned so:
#   - a closer resource beats a farther one even with lower capacity
#   - critical incidents still favor the closest resource over a farther VIP
#   - availability is a hard gate (0 means do not deploy)
W_SEVERITY = 10.0
W_CAPACITY = 8.0
W_AVAILABILITY = 5.0
W_PROXIMITY = 12.0
W_PRIORITY = 4.0

DEFAULT_RADIUS_KM = 25.0
EARTH_RADIUS_KM = 6371.0


# --- Geometry --------------------------------------------------------------
def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points in kilometres."""
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _rough_km2(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Cheap squared-distance approximation in km².

    Uses equirectangular projection — accurate enough at <50 km to act as
    a prefilter without trig. Returns d² (so callers compare against r²).
    At Bangladesh latitudes (~23°N) the error is <2% within a 25 km box.
    """
    mean_lat = math.radians((lat1 + lat2) / 2.0)
    x = math.radians(lng2 - lng1) * math.cos(mean_lat) * EARTH_RADIUS_KM
    y = math.radians(lat2 - lat1) * EARTH_RADIUS_KM
    return x * x + y * y


# --- Scoring helpers -------------------------------------------------------
def _has_coords(r: Dict[str, Any]) -> bool:
    loc = r.get("location") or {}
    coords = loc.get("coords") or {}
    return isinstance(coords.get("lat"), (int, float)) and isinstance(coords.get("lng"), (int, float))


def _capacity_fit(r: Dict[str, Any], incident: Dict[str, Any]) -> float:
    """Returns 0–1 indicating how well a resource's capacity meets the need."""
    rtype = r.get("type")
    needed = max(1, int(incident.get("units_needed", 1)))

    if rtype == "shelter":
        total = r.get("capacity_total") or 0
        used = r.get("capacity_used") or 0
        free = max(0, total - used)
        if free <= 0:
            return 0.0
        affected = int(incident.get("affected_count") or needed)
        return 1.0 if free >= affected else 0.4 * (free / max(affected, 1))

    capacity = r.get("capacity") or 1
    if capacity <= 0:
        return 0.0
    if capacity >= needed:
        return 1.0
    return 0.3 + 0.7 * (capacity / needed)


def _availability_score(r: Dict[str, Any]) -> float:
    """1.0 if available, 0.0 if not. Future: partial credit for limited hours."""
    return 1.0 if r.get("available", True) else 0.0


def _proximity_score(distance_km: float, radius_km: float) -> float:
    """0–1, closer is better. 1 at 0 km, 0 at radius_km."""
    if distance_km <= 0:
        return 1.0
    return max(0.0, 1.0 - (distance_km / max(radius_km, 0.1)))


def _reasons_for(r: Dict[str, Any], distance_km: float, radius_km: float) -> List[str]:
    """Human-readable explanation strings for the dashboard UI."""
    reasons: List[str] = []
    rtype = r.get("type")
    if r.get("priority", 0) > 0:
        reasons.append("Pre-verified / priority resource")
    if distance_km < 2:
        reasons.append(f"Very close ({distance_km:.1f} km)")
    elif distance_km < 5:
        reasons.append(f"Close ({distance_km:.1f} km)")
    else:
        reasons.append(f"{distance_km:.1f} km away")
    if rtype == "shelter":
        total = r.get("capacity_total") or 0
        used = r.get("capacity_used") or 0
        free = max(0, total - used)
        reasons.append(f"{free}/{total} beds free")
    elif rtype in ("ambulance", "rescue_boat"):
        reasons.append(f"Capacity: {r.get('capacity', 1)} patients")
    elif rtype in ("volunteer", "rescue_team", "medical_team"):
        skills = r.get("skills") or []
        if skills:
            reasons.append(f"Skills: {', '.join(skills[:3])}")
    if r.get("tags"):
        reasons.append("Tags: " + ", ".join(r.get("tags")[:2]))
    return reasons


def score_resource(
    r: Dict[str, Any],
    incident: Dict[str, Any],
    distance_km: float,
    radius_km: float = DEFAULT_RADIUS_KM,
) -> float:
    """Compute a single 0–100ish score for a candidate resource.

    The score is a weighted sum:
        score = severity_w  * 10
              + cap_fit     * 8
              + available   * 5
              + proximity   * 12
              + priority    * 4

    Unavailable resources return 0 so they never rank even if they're close.
    """
    if not r.get("available", True):
        return 0.0

    sev_w = SEVERITY_WEIGHT.get(str(incident.get("severity", "medium")).lower(), 2)
    cap_fit = _capacity_fit(r, incident)
    avail = _availability_score(r)
    prox = _proximity_score(distance_km, radius_km)
    prio = max(-2.0, min(2.0, float(r.get("priority", 0)) / 5.0))  # bounded

    return (
        sev_w * W_SEVERITY
        + cap_fit * W_CAPACITY
        + avail * W_AVAILABILITY
        + prox * W_PROXIMITY
        + prio * W_PRIORITY
    )


# --- Prefilter -------------------------------------------------------------
def _overlap(r: Dict[str, Any], wanted: Iterable[str]) -> List[str]:
    return [k for k in (r.get("assistance") or []) if k in wanted]


def prefilter(
    resources: List[Dict[str, Any]],
    incident: Dict[str, Any],
    requested: List[str],
    radius_km: float,
) -> List[Tuple[Dict[str, Any], float, List[str]]]:
    """Return (resource, distance_km², overlapping_assistance) for survivors.

    Drops resources that are:
      - missing coordinates
      - unavailable
      - not providing any of the requested assistance keys
      - outside radius_km (cheap squared-distance test)

    Callers run haversine_km on the survivors — only ~10–30 of them.
    """
    inc_lat = incident.get("lat")
    inc_lng = incident.get("lng")
    if not isinstance(inc_lat, (int, float)) or not isinstance(inc_lng, (int, float)):
        return []

    wanted_set = set(requested or [])
    radius2 = radius_km * radius_km
    survivors: List[Tuple[Dict[str, Any], float, List[str]]] = []

    for r in resources:
        if not r.get("available", True):
            continue
        overlap = _overlap(r, wanted_set)
        if not overlap:
            continue
        if not _has_coords(r):
            continue
        coords = r["location"]["coords"]
        d2 = _rough_km2(inc_lat, inc_lng, coords["lat"], coords["lng"])
        if d2 > radius2:
            continue
        survivors.append((r, d2, overlap))

    return survivors


# --- Public entry point ----------------------------------------------------
def match_for_incident(
    resources: List[Dict[str, Any]],
    incident: Dict[str, Any],
    *,
    requested_assistance: Optional[List[str]] = None,
    radius_km: float = DEFAULT_RADIUS_KM,
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """Return top-N resources per requested assistance key, ranked.

    Output is a list of:
        { "matched_assistance": "<key>",
          "items": [
              { ...resource fields..., "distance_km": float, "score": float,
                "reasons": [str, ...] }
          ] }

    Each `requested_assistance` key gets its own category, even if no
    matches were found — so the frontend can render empty states per slot.
    """
    requested = list(requested_assistance or incident.get("assistance") or [])
    if not requested:
        return []

    survivors = prefilter(resources, incident, requested, radius_km)
    inc_lat = incident["lat"]
    inc_lng = incident["lng"]

    # Bucket by assistance key so each requested slot ranks independently.
    buckets: Dict[str, List[Dict[str, Any]]] = {k: [] for k in requested}
    for r, d2, overlap in survivors:
        coords = r["location"]["coords"]
        dist = haversine_km(inc_lat, inc_lng, coords["lat"], coords["lng"])
        base_score = score_resource(r, incident, dist, radius_km)
        if base_score <= 0:
            continue
        scored = {
            **r,
            "distance_km": round(dist, 2),
            "score": round(base_score, 2),
            "reasons": _reasons_for(r, dist, radius_km),
        }
        # Resource can satisfy multiple assistance slots — duplicate it.
        for key in overlap:
            buckets[key].append(scored)

    # Sort + slice
    out: List[Dict[str, Any]] = []
    for key in requested:
        bucket = buckets[key]
        bucket.sort(key=lambda x: x["score"], reverse=True)
        out.append({"matched_assistance": key, "items": bucket[:top_n]})
    return out


# --- Suggested actions (post-match advice) --------------------------------
def suggest_actions(
    incident: Dict[str, Any],
    categories: List[Dict[str, Any]],
    radius_km: float,
) -> List[str]:
    """Plain-English next steps for the dispatcher / admin dashboard."""
    actions: List[str] = []
    sev = str(incident.get("severity", "medium")).lower()
    missing = [c["matched_assistance"] for c in categories if not c["items"]]

    if sev == "critical":
        actions.append("CRITICAL: dispatch nearest available units immediately and notify on-call coordinator.")
    elif sev == "high":
        actions.append("HIGH priority: confirm dispatch within 15 minutes and stand up a comms channel.")

    if incident.get("immediate_danger"):
        actions.append("Life-at-risk confirmed — page rescue teams first; medical can follow in 5 minutes.")

    if missing:
        pretty = ", ".join(missing)
        actions.append(f"No {pretty} found within {radius_km:.0f} km — escalate to regional cache or request external aid.")

    filled = [c for c in categories if c["items"]]
    if filled and sev in ("medium", "high"):
        actions.append("Notify top-ranked units with the incident brief and ETA from their location.")

    if not actions:
        actions.append("Situation stable — monitor and reassess in 30 minutes.")
    return actions