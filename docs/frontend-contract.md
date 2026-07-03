# Frontend → Backend Contract

> Reverse-direction counterpart to `backend/docs/api.md`.
> This document describes **what the frontend UI currently captures, displays, and expects to consume** — derived from reading the React source under `frontend/src/`. The backend engineer should use it to design (or adjust) endpoints, Pydantic schemas, and MongoDB collections.
>
> **Source files analyzed (read-only):**
> - `user/components/ReportForm.jsx` — primary report submission form
> - `user/pages/ReportIncident.jsx` — submission wrapper + AI preview
> - `user/pages/UserLogin.jsx` + `user/context/UserAuthContext.jsx` — citizen auth
> - `admin/pages/AdminLogin.jsx` + `admin/components/AdminProtectedRoute.jsx` — admin auth
> - `user/pages/IncidentDetail.jsx`, `user/pages/LiveMap.jsx`, `admin/pages/AdminDashboard.jsx` — read views
> - `services/api.js`, `services/mockData.js` — current data shapes and expected endpoint paths
> - `hooks/useReportsList.js`, `hooks/useDashboardStats.js` — filter + aggregation contracts
> - `router.jsx` — route inventory and protection
>
> **Last analyzed:** 2026-07-03

---

## 0. TL;DR — gaps the backend should know about

1. **Citizen signup captures more than the current backend `POST /auth/register` accepts.** The UI collects `fullName`, `nid` (BD national ID, 10 or 13 digits), `phone` (BD format), `email`, `password`. The backend auth endpoint only takes `name`, `email`, `password`, `role`. NID/phone are missing — see §1.
2. **Two divergent data shapes coexist in the frontend.** The form-driven path (`ReportForm` → `ReportIncident`) uses Bangladesh-specific fields (`division/district/upazila`, `immediateDanger`, `incidentTime` enum, `assistance` array). The hook/mock path (`useReportsList`, `mockData.js`) uses a generic shape with `title`, `category`, `severity`, `status`, `hasImage`, `submittedBy`, `ai{}`. They have not been unified. The backend should pick one canonical report schema and align both sides.
3. **Auth is currently a localStorage stub.** The UI does **not** yet call `/auth/*` — `UserAuthContext.jsx` stores users + sessions in `localStorage`. Likewise admin "auth" is `localStorage['rg_admin_auth'] = '1'`. The existing backend JWT endpoints in `api.md` are not yet wired into the UI.
4. **Images are only sent as metadata.** `ReportForm.handleSubmit` strips out the `file` Blob and sends `{name, size, type}` per image. There is no multipart upload or base64 payload in the current form. The backend's report-submission endpoint must accept either a real upload (recommended) or an optional image URL.
5. **List filtering is inconsistent.** `useReportsList` filters by `{status, severity, query}`. `services/api.js` mock hits `/reports?search=&category=&severity=`. `mockData.js` is filtered by `{search, category, severity}` client-side. The backend should pick the canonical query-param names and document them in `api.md`.

---

## 1. Authentication

### 1.1 Citizen — `frontend/src/user/pages/UserLogin.jsx`

A single page with a **Sign in / New sign up** toggle. Each mode is a distinct form.

#### Sign up fields

| Field | UI label | Type | Required | Validation (client-side regex/length) |
|---|---|---|---|---|
| `fullName` | "Full name" | string | yes | non-empty after `trim()`; "As shown on your NID" |
| `nid` | "National ID (NID)" | string | yes | `/^\d{10}$\|^\d{13}$/` — 10 or 13 digits |
| `phone` | "Phone (Bangladesh)" | string | yes | `/^\+?8801[3-9]\d{8}$\|^01[3-9]\d{8}$/` — BD mobile |
| `email` | "Email" | string (email) | yes | `/^[^\s@]+@[^\s@]+\.[^\s@]+$/` (loose RFC) |
| `password` | "Password" | string | yes | `length >= 8` |
| `confirmPassword` | "Confirm password" | string | yes | `=== password` |

Submitting signup calls `signup({ fullName, nid, phone, email, password })` on the auth context — today this is a localStorage write. When wired to the backend it should map to **`POST /auth/register`** but with the **extended user shape** below (currently `register` only accepts `name`, `email`, `password`, `role`).

Suggested request body that the frontend will need to send:
```json
{
  "full_name": "Anwar Hossain",
  "nid": "1234567890123",
  "phone": "+8801712345678",
  "email": "anwar@example.com",
  "password": "strongpass1",
  "role": "citizen"
}
```

> **Backend action:** extend `RegisterRequest` in `backend/app/schemas/auth.py` to add `nid` (10\|13 digits) and `phone` (BD regex). `UserPublic` should expose `nid` and `phone` (not necessarily — admin only). The frontend session will need these on the returned `user` object.

#### Sign in fields

A **single identifier field** that accepts email, phone, **or** NID:

| Field | UI label | Type | Required | Notes |
|---|---|---|---|---|
| `identifier` | "Email, phone, or NID" | string | yes | one of the three — server must try each lookup path |
| `password` | "Password" | string | yes | `>= 1` char in UI (server enforces strength) |

Suggested request body:
```json
{
  "identifier": "anwar@example.com",
  "password": "strongpass1"
}
```

> **Backend action:** either keep the current `/auth/login` (`email` + `password`) and force the frontend to send `email`, **or** add a new `/auth/login` overload that accepts `identifier`. For hackathon speed, the simplest path is to have the frontend resolve the identifier to an email client-side before posting. Pick one and document in `api.md`.

#### Session shape persisted client-side

From `writeSession()` in `UserAuthContext.jsx`:
```json
{
  "id": "u_abc123",
  "fullName": "Anwar Hossain",
  "email": "anwar@example.com",
  "phone": "+8801712345678",
  "nid": "1234567890123",
  "signedInAt": "2026-07-03T11:04:55.754Z"
}
```

> **Backend action:** the `/auth/me` response should include `full_name`, `phone`, `nid` so the frontend can rehydrate the session on reload without losing fields. Currently `UserPublic` returns `name` only.

#### localStorage keys (existing, do not break)
- `rg_user_registry_v1` — array of all users (frontend mock)
- `rg_user_session_v1` — current session object above

When the backend is wired, these localStorage paths should be replaced with the JWT in `Authorization: Bearer …` and a session in React state.

---

### 1.2 Admin — `frontend/src/admin/pages/AdminLogin.jsx`

#### Login fields

| Field | UI label | Type | Required | Notes |
|---|---|---|---|---|
| `adminId` | "Admin ID" | string | yes | placeholder `admin@reliefgrid` — expected to be email/username |
| `password` | "Password" | string | yes | non-empty |

Current stub: any non-empty values pass; sets `localStorage['rg_admin_auth'] = '1'` and navigates to `/admin/dashboard`. The card footer explicitly says *"Demo build — authentication is mocked. The dashboard will be wired in the next step."*

Suggested real implementation: post to the same `POST /auth/login` with `role` resolution server-side. Or add `POST /auth/admin/login`. Recommended: reuse `/auth/login`, then on success check the returned `user.role === "admin"`; if not, return 403.

#### Admin session flag
- `localStorage['rg_admin_auth'] = '1'` — when backend JWT is wired, this should be replaced by a check on the access token's `role` claim + a follow-up `/auth/me` call.

#### Route protection
`AdminProtectedRoute.jsx` checks `localStorage.getItem('rg_admin_auth') === '1'`. When backend lands, this component should instead use the JWT's `role` (decode or call `/auth/me`).

---

## 2. Report submission — `frontend/src/user/components/ReportForm.jsx`

This is the form a citizen fills in to report an emergency. Eight sections, in order. All fields are client-trimmed; the only required-enforced fields at submit time are `division` and `description` (see `ReportIncident.handleSubmit`).

### 2.1 Location (Section 1)

`location` is a nested object on the payload:
```json
{
  "division": "Dhaka",
  "district": "Gazipur",
  "upazila": "Kaliakair",
  "area": "Baipail industrial zone",
  "coords": { "lat": 24.0693, "lng": 90.2221 }
}
```

| Field | Source | Type | Required | Notes |
|---|---|---|---|---|
| `division` | `<select>` | enum | **yes** (validated in wrapper) | One of 8: `Dhaka`, `Chittagong`, `Rajshahi`, `Khulna`, `Barisal`, `Sylhet`, `Rangpur`, `Mymensingh` |
| `district` | `<select>` (filtered by division) | enum | optional | Hardcoded list per division in `BD_LOCATIONS` |
| `upazila` | `<select>` | enum | optional | `getUpazilas()` currently returns `[]` — feature is scaffolded but empty |
| `area` | `<input>` text | string | optional | "Village, neighborhood, or nearest landmark"; `trim()` not applied client-side |
| `coords.lat` | `navigator.geolocation` | number | optional | set by "Use my current location" button |
| `coords.lng` | `navigator.geolocation` | number | optional | paired with `lat` |

> **Backend action:** if the backend wants to validate division/district, mirror the 8-division list. Hardcoded lists in the frontend will drift from a server-side reference — either keep division/district as free strings or have a `/locations/divisions` endpoint.

### 2.2 Description (Section 2)

| Field | Type | Required | Validation |
|---|---|---|---|
| `description` | string (textarea, 6 rows) | **yes** (validated in wrapper) | `<Textarea required>`; non-empty after `trim()` |

> This is the single most important field — it is the raw text the AI pipeline will structure. **Max length:** no client cap. Recommend `min_length=10`, `max_length=4000` server-side.

### 2.3 Images (Section 3)

Dropzone, max 5 images, max 6MB each, `image/*` mime only.

`images` in the current `handleSubmit` payload is mapped to:
```json
[
  { "name": "flood1.jpg", "size": 482113, "type": "image/jpeg" }
]
```

— i.e. **metadata only, the `File` Blob is dropped**. The frontend does not yet do a real upload.

> **Backend action:** the `POST /api/report/submit` endpoint must decide on a contract for images. Three options, pick one:
> 1. **Multipart upload** — `multipart/form-data` with `image` files[] + JSON fields. Requires a second endpoint or a form-data variant.
> 2. **Base64 in JSON** — convenient for single-call submit; blows up payload size; not recommended for >1 MB.
> 3. **Image URL** — frontend uploads to object storage (S3/Cloudinary) and sends the URL. Requires a separate upload endpoint, e.g. `POST /api/uploads` returning `{url}`.
>
> For hackathon speed: option 1 (multipart) is the simplest if the backend can accept files alongside fields. Either way, **the frontend will need an update to actually send the file**, which is not the case today.

### 2.4 Affected people (Section 4)

| Field | Type | Required | Validation |
|---|---|---|---|
| `affectedCount` | number (integer) | optional | `type="number" min="0" inputMode="numeric"`; empty string → `null` |

Sent as `affectedCount: affectedCount ? Number(affectedCount) : null` — i.e. `null` when blank.

### 2.5 Required assistance (Section 5)

Multi-select chips. The full enum (these are the **only** valid keys):
```
rescue_team, food, water, medical, shelter, medicine,
ambulance, rescue_boat, baby_supplies, clothes, other
```

Sent as `assistance: string[]` (zero or more of the above).

> **Backend action:** validate against this enum. Note `fire_service` appears in the **mock data** (`useReportsList` SEED_REPORTS) but is **not** in the form's options — the chip set is the source of truth. Either add `fire_service` to the form or remove it from seeds.

### 2.6 Immediate danger (Section 6)

Radio button: `yes` / `no`. Sent as `immediateDanger: boolean` (`immediateDanger === 'yes'`).

### 2.7 Incident time (Section 7)

Single-select dropdown. Enum:
```
just_now | within_1h | today | yesterday | older
```

Sent as `incidentTime: string` (one of the above, or empty string `""` if unselected).

> **Backend action:** validate against the enum; allow `""`/null. If you want a real `incident_occurred_at` timestamp, derive it from `incidentTime` + `submittedAt` server-side, or have the UI send it directly later.

### 2.8 Additional notes (Section 8)

| Field | Type | Required | Notes |
|---|---|---|---|
| `notes` | string (textarea, 4 rows) | optional | `trim()` applied |

### 2.9 Client-generated timestamp

`submittedAt: new Date().toISOString()` — added in `handleSubmit`. Server should **always** set its own `created_at` (don't trust the client clock) and use that for sort. Optionally store the client value for audit.

### 2.10 Full submit payload shape

```json
{
  "description": "Flood water rising in the village, families on rooftops…",
  "images": [{ "name": "flood1.jpg", "size": 482113, "type": "image/jpeg" }],
  "affectedCount": 120,
  "assistance": ["rescue_team", "rescue_boat", "shelter"],
  "immediateDanger": true,
  "incidentTime": "within_1h",
  "notes": "Local contact: 01712-345678 (Rahim, school teacher)",
  "location": {
    "division": "Rangpur",
    "district": "Kurigram",
    "upazila": "Nageshwari",
    "area": "Ward 3, beside the embankment",
    "coords": { "lat": 25.8057, "lng": 89.6361 }
  },
  "submittedAt": "2026-07-03T11:42:00.000Z"
}
```

This matches the existing `POST /api/report/submit` plan but with two gaps:
- No `user_id` (the form does not pass who is submitting). The backend should attach this from the JWT.
- No `title` field. The current plan in `api.md` does not show `title`, but `mockData.js` and `services/api.js` both use `title` for list rendering. **Add `title` to the form or remove `title` from the list view.**

---

## 3. Report list / filtering — `useReportsList.js` + `api.js`

### 3.1 Filter contract (per hook)

```js
filter: { status: 'all' | string, severity: 'all' | string, query: string }
```

`query` is a free-text search that matches (case-insensitive) against: `title`, `area`, `district`, `upazila`, `category`. Sort: newest first by `createdAt`/`submittedAt`.

### 3.2 Endpoint contract (per `api.js`)

```http
GET /reports?search=<q>&category=<cat>&severity=<sev>
GET /reports/{id}
POST /reports
GET /dashboard/stats
```

> **Backend action:** these are the endpoint paths the frontend is **configured to call** when `VITE_USE_MOCK=false`. The current backend plan in `puku.md` uses `/api/report/*` and `/api/reports` (singular `report`). Align one of:
> - Change frontend to `/api/report/submit`, `/api/report/{id}`, `/api/reports` (1-line changes in `api.js`).
> - Or alias the new endpoints to match the frontend paths.
>
> Pick the backend's preferred paths and update both `api.js` and this document.

### 3.3 Status enum — currently inconsistent in the frontend

The frontend uses **two different status vocabularies**:

`useReportsList` SEED_REPORTS uses:
```
pending, verified, dispatched
```

`mockData.js` (`api.js` SAMPLE_REPORTS) uses:
```
pending, in_review, action_required, resolved
```

The admin dashboard's stats are derived assuming `verified`/`dispatched` count as "active" (from `useDashboardStats`). Pick **one** canonical enum for the backend and align both frontend data sources.

> **Recommended:** `pending | verified | dispatched | resolved` (matches the SEED flow). If you want an "in review" intermediate state, add `in_review` between `pending` and `verified`.

### 3.4 Severity enum — also inconsistent

`ReportForm` flow (and the AI preview in `ReportIncident`) uses **Title Case**:
```
Critical | High | Medium | Low
```

`mockData.js` and `useDashboardStats` use **lowercase**:
```
critical | high | medium | low
```

> **Backend action:** store severity as one canonical form (recommend lowercase per `SEVERITY_LEVELS` in `mockData.js`) and have the UI map the case for display. Document in `api.md`.

### 3.5 Expected response shape per report (list & detail)

Based on `mockCreateReport` in `api.js` (this is the shape `services/api.js` will deserialize into a card):

```json
{
  "id": "RPT-1001",
  "title": "Flash flood in Kurigram",
  "description": "…",
  "category": "Flood / Water Rescue",
  "severity": "Critical",
  "status": "verified",
  "location": "Ward 3, beside the embankment",
  "hasImage": true,
  "imageUrl": "https://…/rpt-1001.jpg",
  "submittedBy": "Anwar Hossain",
  "submittedAt": "2026-07-02T11:42:00.000Z",
  "ai": {
    "summary": "…",
    "category": "Flood / Water Rescue",
    "severity": "Critical",
    "sentiment": "negative",
    "confidence": 0.91,
    "keywords": ["flood", "rescue"],
    "entities": { "locations": ["…"], "people": [], "organizations": [] },
    "recommendations": ["…"]
  }
}
```

And the alternative (Bangladesh-specific) shape used by `useReportsList`:

```json
{
  "id": "rpt_001",
  "title": "Flash flood in Kurigram",
  "category": "Flood / Water Rescue",
  "severity": "Critical",
  "division": "Rangpur",
  "district": "Kurigram",
  "upazila": "Nageshwari",
  "area": "Ward 3, beside the embankment",
  "affectedCount": 320,
  "assistance": ["rescue_team", "water", "shelter", "rescue_boat"],
  "immediateDanger": true,
  "incidentTime": "just_now",
  "status": "verified",
  "createdAt": "2026-07-02T11:42:00.000Z",
  "coords": { "lat": 25.8057, "lng": 89.6361 }
}
```

> **Backend action:** design the **canonical** schema to be a union — the response should include the BD location fields (`division`, `district`, `upazila`, `area`, `coords`) **and** the flat fields (`category`, `severity`, `status`, `title`, `submittedBy`, `imageUrl`, `submittedAt`, `ai{}`). Both frontend data consumers will then work off one payload.

---

## 4. AI structured output (preview in `ReportIncident.jsx`)

After submit, the frontend shows a preview built by `buildMockAnalysis()`. This is the **shape the AI endpoint should return** for the post-submit preview (and which can be stored alongside the raw report in MongoDB):

```ts
{
  category: "Flood / Water Rescue" | "Fire" | "Structural Collapse"
          | "Medical Emergency" | "Earthquake" | "General Emergency",
  severity: "Critical" | "High" | "Medium" | "Low",
  urgencyScore: number,            // 0–160 in the mock; suggest clamping to 0–100
  entities: string[],              // human-readable extracted facts
  keywords: string[],              // top 4+-letter words from description
  recommendedRelief: string[],     // subset of assistance[] keys
  location: { ...full location... },
  summary: string                  // ≤ 220 chars in mock
}
```

Category heuristics from the mock (for reference — the real AI will do better):
- `flood|water|boat|river|monsoon` → `Flood / Water Rescue`
- `fire|smoke|burn` → `Fire`
- `building|collapse|wall|roof` → `Structural Collapse`
- `medic|injured|injury|hospital|doctor` → `Medical Emergency`
- `earthquake|quake|tremor` → `Earthquake`
- else → `General Emergency`

Severity heuristic from the mock (this is what the AI's structured output will be validated against at minimum):
- `danger && count >= 50` → `Critical`
- `danger || count >= 20` → `High`
- `!danger && count === 0` → `Low`
- else → `Medium`

Urgency score (mock formula, not authoritative):
```
(danger ? 50 : 10) + min(affectedCount, 50) + assistance.length * 4
```

> **Backend action:** the AI pipeline in `puku.md` already specifies `{type, severity, summary, recommendation, urgency_score}`. The frontend mock uses **different field names** (`category` not `type`, `recommendedRelief`/`recommendations` not `recommendation`). Map:
> - backend `type` → frontend `category`
> - backend `recommendation` (string) → frontend `recommendations` (string[])
> - backend `urgency_score` → frontend `urgencyScore`
>
> Decide which side renames, then update `api.md`.

---

## 5. Dashboard stats — `useDashboardStats.js`

The hook derives from the same reports list and expects these fields on every report:
- `severity` (string, used to bucket into `Critical/High/Medium/Low`)
- `status` (string, used to compute `active` count: `verified | dispatched`)
- `affectedCount` (number, summed)
- `immediateDanger` (boolean, counted when true)
- `assistance` (array of strings, tallied per key)
- `division` (string, tallied per key)

Derived response shape:
```json
{
  "total": 8,
  "critical": 2,
  "active": 4,
  "affectedPeople": 612,
  "dangerActive": 3,
  "reliefTallies": [{ "key": "rescue_team", "label": "Rescue Teams", "count": 4 }, ...],
  "divisionTallies": [{ "division": "Dhaka", "count": 2 }, ...],
  "severityTallies": [
    { "severity": "Critical", "count": 2 },
    { "severity": "High", "count": 3 },
    { "severity": "Medium", "count": 2 },
    { "severity": "Low", "count": 1 }
  ]
}
```

The admin dashboard currently shows hardcoded `—` for the top four stat cards (`Active incidents`, `Critical zones`, `Rescues dispatched`, `Avg. response time`). When backend lands, map these to:
- `Active incidents` → `stats.active`
- `Critical zones` → `stats.critical` (or `stats.divisionTallies` filtered to top)
- `Rescues dispatched` → count of `status === "dispatched"`
- `Avg. response time` → not yet derivable from current data; needs a new `dispatchedAt`/`resolvedAt` field on the report

---

## 6. Route inventory (from `router.jsx`)

| Path | Component | Protection |
|---|---|---|
| `/` | `Landing` | public |
| `/login` | `UserLogin` | public; redirects to `from` if already authed |
| `/report` | `ReportIncident` | `UserProtectedRoute` (citizen must be signed in) |
| `/incidents` | (list page) | public |
| `/incidents/:id` | `IncidentDetail` | public |
| `/map` | `LiveMap` | public |
| `/admin/login` | `AdminLogin` | public; if `rg_admin_auth` is `'1'`, redirect away |
| `/admin/dashboard` | `AdminDashboard` | `AdminProtectedRoute` (admin must be signed in) |

> **Backend action:** `/report` and `/admin/dashboard` are protected client-side only. The API endpoints that back them (e.g. `POST /api/report/submit`, `GET /api/reports`) **must also enforce** the same role gates server-side using the `require_role` dep from `backend/app/core/security.py`. See `api.md` for the JWT/role mechanics.

---

## 7. Existing backend artifacts to reuse

The backend already has these built and ready to wire up to the frontend (see `backend/docs/api.md` for the auth side):

- `POST /auth/register` — extend schema to accept `nid` and `phone` (§1.1).
- `POST /auth/login` — either rename to accept `identifier` or keep as email-only and update the frontend.
- `GET /auth/me` — extend `UserPublic` to include `nid` and `phone` so the session rehydrates.
- `require_role("admin")` — already exists in `app/core/security.py`; use it on any admin endpoint.
- `POST /api/report/submit`, `GET /api/report/{id}`, `GET /api/reports` — planned in `puku.md` §REQUIRED API ENDPOINTS; align paths with `api.js` (§3.2).

---

## 8. Suggested MongoDB collections

These follow the existing single-collection principle from `puku.md` (no over-normalization), with one extra collection for the user-specific fields.

### 8.1 `users` (already exists)

```jsonc
{
  "_id": ObjectId,
  "name": "Anwar Hossain",
  "email": "anwar@example.com",  // unique index
  "password_hash": "bcrypt…",
  "role": "citizen",              // "citizen" | "admin"
  "nid": "1234567890123",         // NEW — 10 or 13 digits
  "phone": "+8801712345678",      // NEW — BD format
  "created_at": ISODate,
  "updated_at": ISODate
}
```

Indexes: unique on `email`; consider unique on `nid` and `phone` for citizen identity.

### 8.2 `reports` (already planned)

A single document per submitted incident. Suggested shape (union of both frontend data shapes):

```jsonc
{
  "_id": ObjectId,
  "id": "RPT-1001",                      // human-friendly id
  "user_id": ObjectId,                   // ref to users._id (from JWT)

  // raw input
  "title": "Flash flood in Kurigram",    // derived/optional
  "description": "Flood water rising…",
  "images": [
    { "url": "https://…/rpt-1001-1.jpg", "name": "flood1.jpg", "size": 482113, "type": "image/jpeg" }
  ],
  "affected_count": 320,
  "assistance": ["rescue_team", "water", "shelter", "rescue_boat"],
  "immediate_danger": true,
  "incident_time": "within_1h",          // enum from §2.7
  "notes": "Local contact: 01712-…",
  "location": {
    "division": "Rangpur",
    "district": "Kurigram",
    "upazila": "Nageshwari",
    "area": "Ward 3, beside the embankment",
    "coords": { "type": "Point", "lat": 25.8057, "lng": 89.6361 }   // GeoJSON-ready
  },

  // AI output
  "ai": {
    "type": "Flood / Water Rescue",      // matches frontend "category"
    "severity": "critical",              // canonical lowercase
    "summary": "…",
    "recommendations": ["…"],            // array of strings
    "urgency_score": 87,
    "keywords": ["flood", "rescue"],
    "entities": { "locations": [], "people": [], "organizations": [] },
    "confidence": 0.91,
    "model": "gpt-4o-mini",
    "generated_at": ISODate
  },

  // workflow
  "status": "verified",                  // pending | verified | dispatched | resolved
  "submitted_at": ISODate,               // server clock
  "created_at": ISODate,                 // alias
  "updated_at": ISODate,
  "verified_by": ObjectId | null,        // admin user
  "dispatched_at": ISODate | null,
  "resolved_at": ISODate | null
}
```

Indexes:
- `{ status: 1, created_at: -1 }` — dashboard list, latest first
- `{ "ai.severity": 1, created_at: -1 }` — severity filters
- `{ "location.division": 1, "location.district": 1 }` — geo filters
- `{ "location.coords": "2dsphere" }` — only if/when geo queries are added
- text index on `description`, `notes`, `title` for full-text search (or use regex like the frontend mock)

> No second collection for AI insights — keep it embedded per the `puku.md` rule *"Do NOT over-normalize schema."*

---

## 9. Open decisions for the backend engineer

1. **Path prefix** — `/api/reports` (current backend plan) vs `/reports` (what `api.js` calls). One line in `api.js` to align.
2. **`category` vs `type`** — backend `ai.type` ↔ frontend `category`. Pick a canonical name and update the OpenAI prompt + the Pydantic schema + `api.md`.
3. **`urgency_score` range** — clamp to 0–100 (per the original `puku.md` spec) or allow higher (the mock formula goes up to ~160).
4. **Identifier-based login** — keep `/auth/login` email-only and update the frontend, or add `identifier`-based login on the backend.
5. **`nid` / `phone` on `UserPublic`** — return them in `/auth/me` so the session persists them, or keep them internal and re-prompt.
6. **Status enum** — pick one of `{pending, verified, dispatched, resolved}` or `{pending, in_review, action_required, resolved}`. Recommended: the first set.
7. **Severity casing** — lowercase in storage, Title case in display (UI responsibility).
8. **Image upload mechanism** — multipart vs base64 vs URL-after-upload. Recommended: multipart on `POST /api/report/submit` for hackathon speed; introduce a separate `/api/uploads` later if needed.
9. **`title` field** — generate server-side from the first sentence of `description` if not provided, or have the UI collect it.

---

## 10. Things the frontend does **not** currently do

Worth flagging so the backend doesn't over-build:

- No pagination (the list is rendered in full). The mock always returns the full SAMPLE_REPORTS array. Add `?limit=&offset=` only when the dashboard needs it.
- No sorting controls — sort is always `createdAt DESC`. Skip sort params for now.
- No real-time updates (no websocket / SSE). Polling is fine for the demo.
- No "edit report" or "delete report" — the admin dashboard's `updateStatus(id, status)` is in the hook but not surfaced in the UI yet. Add a `PATCH /api/reports/{id}/status` endpoint when the admin UI catches up.
- No "my reports" view for citizens — the user-side list is global.
- `IncidentDetail` and `LiveMap` are placeholders — they will need full schemas when wired, but the list response shape is enough for now.

---

*This document is read-only analysis of the frontend. No frontend code was modified. Update this file whenever the frontend's form fields or expected API contract change.*
