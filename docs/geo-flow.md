# Geo-tagging & Location Intelligence — End-to-End Flow

This document describes how location moves from the citizen's phone through
the backend into the authority dashboard map. It is intentionally split into
**what the frontend owns**, **what the backend already serves**, and
**what is still pending** (a small bounding-box endpoint + a hotspots
endpoint for the bonus).

---

## 1. Citizen submits a report — location data path

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser (ReportForm.jsx)                                            │
│                                                                      │
│   Option A: "Use my current location" button                         │
│     └─> navigator.geolocation.getCurrentPosition()                  │
│         └─> { lat, lng } → state.coords                             │
│                                                                      │
│   Option B: Manual entry                                             │
│     └─> division dropdown (required)                                │
│         └─> district dropdown (optional, filtered by division)       │
│             └─> upazila dropdown (scaffolded, empty for now)        │
│                 └─> area text input ("village / landmark")          │
│                                                                      │
│   handleSubmit() builds:                                             │
│     {                                                                │
│       description: "...",                                           │
│       location: {                                                    │
│         division: "Sylhet",                                          │
│         district: "Sunamganj",                                       │
│         upazila: null,                                               │
│         area: "Beanibazar",                                          │
│         coords: { lat: 24.84, lng: 91.41 }                           │
│       },                                                             │
│       ...                                                            │
│     }                                                                │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              │  multipart/form-data POST
                              │  /api/report/submit
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Backend (FastAPI)                                                   │
│                                                                      │
│   1. Pydantic validation (ReportSubmitRequest)                       │
│      - location.division required (≥1 char after trim)               │
│      - coords.lat / coords.lng optional floats                       │
│                                                                      │
│   2. MongoDB insert (reports collection)                             │
│      doc = {                                                         │
│        description, location{division,district,...,coords},          │
│        status: "pending_ai",                                         │
│        created_at: <server clock>                                    │
│      }                                                               │
│      2dsphere index on location.coords   ← indexed for geo queries   │
│                                                                      │
│   3. Returns 201 with serialized doc                                 │
└──────────────────────────────────────────────────────────────────────┘
```

The backend **never geocodes the division/district into lat/lng** — it trusts
the client. This is intentional: (a) free-tier geocoding APIs have hard rate
limits and would be exhausted in demo traffic, (b) the client's
`navigator.geolocation` is already authoritative when the citizen opts in,
(c) the optional `area` text is best resolved client-side with the same
map provider the dashboard uses (visual consistency).

---

## 2. Authority dashboard loads the map

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser (LiveMap.jsx + useReportsList hook)                         │
│                                                                      │
│   On mount:                                                          │
│     1. GET /api/reports?limit=500                                    │
│        → returns latest 500 reports with full location.coords       │
│                                                                      │
│     2. For each report where coords != null:                         │
│        Leaflet L.marker([lat, lng])                                  │
│        L.markerClusterGroup({                                        │
│          maxClusterRadius: 60,                                       │
│          disableClusteringAtZoom: 14                                 │
│        })                                                            │
│                                                                      │
│     3. On map pan/zoom end:                                          │
│        (optional) GET /api/reports?bbox=west,south,east,north        │
│        → replaces markers with only the visible reports              │
└──────────────────────────────────────────────────────────────────────┘
                              ▲
                              │
                              │  GET /api/reports (JSON)
                              │
┌──────────────────────────────────────────────────────────────────────┐
│  Backend                                                             │
│                                                                      │
│   GET /api/reports                                                   │
│     Query params:                                                    │
│       - limit  (default 100, max 500)                                │
│       - bbox   (west,south,east,north — WGS84)        [TO ADD]       │
│       - type, severity, since    [TO ADD]                            │
│                                                                      │
│     Mongo query (when bbox provided):                                │
│       {                                                               │
│         "location.coords": {                                         │
│           $geoWithin: { $geometry: {                                 │
│             type: "Polygon",                                         │
│             coordinates: [[[w,s],[e,s],[e,n],[w,n],[w,s]]]          │
│           }}                                                         │
│         }                                                            │
│       }                                                              │
│     Sort: created_at desc                                            │
│                                                                      │
│     Response: { items: ReportOut[], count: int }                     │
└──────────────────────────────────────────────────────────────────────┘
```

Clustering happens **client-side**. The backend does not need a clustering
endpoint — sending 500 records to Leaflet and letting `markerClusterGroup`
handle it is fast and zero-cost on the server. Doing it on the server would
mean re-running clustering on every viewport change.

---

## 3. Hotspot auto-detection (bonus)

This is the only piece that genuinely needs new backend work.

```
┌──────────────────────────────────────────────────────────────────────┐
│  GET /api/geo/hotspots?window=24h&grid=0.05                         │
│                                                                      │
│  1. Load all reports with coords in the last `window`               │
│                                                                      │
│  2. Snap each report's (lat, lng) to a 0.05° grid cell               │
│     cell_id = f"{round(lat/0.05)}_{round(lng/0.05)}"                 │
│                                                                      │
│  3. Aggregate per cell:                                              │
│     - count of reports                                               │
│     - avg severity, max urgency_score                                │
│     - top disaster type                                              │
│     - list of report ids                                             │
│                                                                      │
│  4. Filter cells with count >= 3 (configurable)                      │
│                                                                      │
│  5. Sort by severity_score desc (severity weight × count)           │
│                                                                      │
│  Response:                                                           │
│  {                                                                   │
│    "hotspots": [                                                     │
│      {                                                               │
│        "cell": { "lat": 24.85, "lng": 91.40, "radius_km": 5 },       │
│        "count": 12,                                                  │
│        "avg_severity": "high",                                       │
│        "max_urgency": 92,                                            │
│        "top_type": "flood",                                          │
│        "report_ids": [...]                                           │
│      },                                                              │
│      ...                                                             │
│    ],                                                                │
│    "window_hours": 24,                                               │
│    "generated_at": "..."                                             │
│  }                                                                   │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Dashboard (LiveMap.jsx)                                             │
│     L.geoJSON(hotspots, {                                           │
│       style: { color: severity_color(hotspot.avg_severity) },        │
│       pointToLayer: (f, latlng) => L.circle(latlng, f.cell.radius) │
│     })                                                               │
│     .bindPopup(`<b>${f.top_type}</b><br>${f.count} reports`)        │
└──────────────────────────────────────────────────────────────────────┘
```

For a hackathon-grade demo, **grid-bucket aggregation in pure Python is
fine** — 500–2000 reports fits in memory. A proper implementation would use
MongoDB's `$geoNear` + `$group`, but that's an optimization, not a
correctness requirement.

---

## 4. What is already complete vs pending

| # | Capability | Owner | Status |
|---|---|---|---|
| 1 | Detect location (browser geo) | frontend | ✅ done |
| 2 | Manual location input | frontend | ✅ done |
| 3 | Accept coords on submit | backend | ✅ done (`Coords` schema, stored in Mongo) |
| 4 | Serve report list for map | backend | ✅ done (`GET /api/reports`) |
| 5 | Render pins on live map | frontend | ✅ done (`LiveMap.jsx`) |
| 6 | Client-side clustering | frontend | ✅ done (`markerClusterGroup`) |
| 7 | Bounding-box query (perf) | backend | ⚠️ to add |
| 8 | Auto-detect hotspots (bonus) | backend | ⚠️ to add |

---

## 5. Recommended next steps

1. **Add `GET /api/reports?bbox=...`** to `routes/report.py` — small, ~30 lines,
   uses Mongo's `$geoWithin`. Lets the dashboard load only the visible
   viewport instead of all 500 records at once.
2. **Add `GET /api/geo/hotspots`** to a new `routes/geo.py` — pure-Python
   grid aggregation over the last 24h of reports with coords. Renders as
   colored circles on the same map.
3. **Frontend hookup** (out of backend scope) — `LiveMap.jsx` calls the new
   bbox endpoint on `moveend`, and overlays hotspot circles from the
   hotspots endpoint on a toggle.

Step 1 and 2 are independent — step 1 can ship first because it has zero
frontend dependencies (existing `GET /api/reports` keeps working).