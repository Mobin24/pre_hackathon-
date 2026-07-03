# DRRCS API · Backend → Frontend

> The canonical contract the frontend (React, under `frontend/`) talks to.
> Every endpoint documented here lives in `backend/app/routes/`.
>
> **Base URL (local dev):** `http://localhost:8000`
> **OpenAPI / Swagger UI:** `http://localhost:8000/docs`
> **OpenAPI JSON:** `http://localhost:8000/openapi.json`
> **Health check:** `GET http://localhost:8000/health` → `{ "status": "ok", "mongo": "ok" | "not_configured" | "error: …" }`
>
> **Auth model:** JWT bearer. Token from `/auth/login` or `/auth/register`. Send it on every non-auth call as:
> `Authorization: Bearer <access_token>`
>
> **Last updated:** 2026-07-04

---

## Table of contents

1. [Endpoint → UI mapping table](#1-endpoint--ui-mapping-table)
2. [Quick reference for every endpoint](#2-quick-reference-for-every-endpoint)
3. [Conventions: errors, status codes, content types](#3-conventions-errors-status-codes-content-types)
4. [All edge cases the frontend must handle](#4-all-edge-cases-the-frontend-must-handle)
5. [Safely establishing the connection from the frontend](#5-safely-establishing-the-connection-from-the-frontend)
6. [Troubleshooting checklist](#6-troubleshooting-checklist)

---

## 1. Endpoint → UI mapping table

Every HTTP endpoint the backend exposes, written in plain language, with a pointer to where the UI shows or submits it. Use the in-file pointer as a quick “where do I wire this?” — the next section lists the actual shapes.

| # | Method | Path | Auth | Where it lives in the UI | Plain-language summary |
|---|---|---|---|---|---|
| 1 | `POST` | `/auth/register` | none | **`UserLogin.jsx`** → “New sign up” form | Create a citizen account (email + phone + BD NID + password). Returns a token so the UI can land the user straight on `/report`. |
| 2 | `POST` | `/auth/login` | none | **`UserLogin.jsx`** → “Sign in” form **and** `AdminLogin.jsx` | Sign in with email, phone, or NID. Same endpoint for citizens and admins — `role` is read server-side from the DB. |
| 3 | `GET` | `/auth/me` | required | **`UserAuthContext.jsx`** + **`AdminProtectedRoute.jsx`** | Returns the logged-in user’s public profile. Used to rehydrate the session on reload and to check the role. |
| 4 | `POST` | `/api/report/submit` | required (citizen) | **`ReportIncident.jsx`** → `ReportForm.jsx` submit button | Citizen submits a new incident. Multipart form — fields + one or more image files. Triggers the AI pipeline (returns immediately, AI runs in the background). |
| 5 | `GET` | `/api/report/{id}` | required (owner or admin) | **`IncidentDetail.jsx`**, dashboard incident modal | Fetch one processed report. Citizens see only their own; admins see everything. |
| 6 | `GET` | `/api/report/{id}/images/{filename}` | none (public URL) | Wherever a report image is rendered | Streams the stored image bytes back. The report response includes fully-qualified `images[].url` already, so this is mostly for previews/sharing. |
| 7 | `GET` | `/api/reports` | required (citizen sees own; admin sees all) | **`hooks/useReportsList.js`**, `services/api.js` `reportsApi.list` | List of reports, newest first. Supports `bbox`, `limit`, `offset` filtering. |
| 8 | `PATCH` | `/api/reports/{id}/status` | admin | Admin dashboard → status chip / kebab menu | Admin advances the pipeline state (`pending_ai` ↔ `processed` / `failed` / `resolved`). Returns the updated report. |
| 9 | `POST` | `/api/admin/reports/{id}/reprocess` | admin | Admin dashboard → “Re-run AI” button | Force the AI pipeline to run again on an already-processed report. |
| 10 | `POST` | `/api/match/{report_id}` | required (owner or admin) | Dashboard → “Find relief” / `IncidentDetail.jsx` match panel | Ranked list of nearby resources for an incident. Commits nothing; safe to call repeatedly. |
| 11 | `GET` | `/api/match/{report_id}/preview` | required (owner or admin) | Same panel → dry-run toggle | Same as #10 but a `GET`, handy for previews. |
| 12 | `GET` | `/api/dashboard/stats` | admin | **`AdminDashboard.jsx`** stat tiles | Severity / status / resource counts for the dashboard top row. |
| 13 | `GET` | `/api/dashboard/incidents` | admin | **`AdminDashboard.jsx`** incident table | Severity-first ranked list of incidents. Supports `severity`, `status`, `bbox`, `limit`, `offset`. |
| 14 | `GET` | `/api/dashboard/incidents/{id}` | admin | **`AdminDashboard.jsx`** incident modal | One incident, full shape. |
| 15 | `POST` | `/api/dashboard/incidents/{id}/dispatch` | admin | **`AdminDashboard.jsx`** → “Dispatch” button | Mark resources as dispatched to an incident. Body: `{ "resource_ids": [...], "notes": "..." }`. |
| 16 | `POST` | `/api/dashboard/incidents/{id}/resolve` | admin | **`AdminDashboard.jsx`** → “Resolve” button | Mark an incident resolved; optionally restores the dispatched resources. |
| 17 | `GET` | `/api/dashboard/feed` | admin | **`AdminDashboard.jsx`** polled every 5–10s | One-call bundle: `stats` + recent incidents + available resources. The polling endpoint. |
| 18 | `GET` | `/api/geo/hotspots` | required | **`LiveMap.jsx`** heatmap layer | Aggregated incident density per geo cell for the live map. |
| 19 | `GET` | `/api/resources` | required (admin for full; citizens see only `available:true`) | **`AdminDashboard.jsx`** resources rail | List of relief resources. |
| 20 | `GET` | `/api/resources/{resource_id}` | required | Detail panels | One resource. |
| 21 | `PATCH` | `/api/resources/{resource_id}/availability` | admin | **`AdminDashboard.jsx`** toggle | Flip a resource between `available:true/false`. |
| 22 | `POST` | `/api/resources/reset` | admin | Admin → “Reset demo data” button | Reset every resource to `available:true` (demo helper). |
| 23 | `POST` | `/api/sitrep/generate` | admin | Admin → “Generate sitrep” button | Force a fresh situation report (also auto-generated every hour by the server). |
| 24 | `GET` | `/api/sitrep/latest` | admin | Admin → top-of-page headline strip | Returns the most recent sitrep, optionally filtered by divisions. |
| 25 | `GET` | `/api/sitrep` | admin | Admin → sitrep history list | Recent N sitreps. |
| 26 | `GET` | `/api/sitrep/{sitrep_id}` | admin | Admin → click a sitrep to expand | One sitrep. |
| 27 | `GET` | `/api/sitrep/{sitrep_id}/export` | admin | Admin → “Export” button | Downloads the sitrep as text or PDF. |

> The frontend today only calls a handful of these directly (the ones in `frontend/src/services/api.js` plus the auth + report-submit endpoints). Everything else should be added to `services/api.js` as the UI grows. Keep the URL string inside that file as the single source of truth.

---

## 2. Quick reference for every endpoint

The shapes below are what actually goes over the wire. Anything you see in `ReportOut` / `UserPublic` / `ResourceOut` is the result of Pydantic’s serialization — if a field is `Optional`, the key may be omitted (or `null`); handle both.

### 2.1 Auth

**`POST /auth/register`** — register a citizen
```http
POST /auth/register
Content-Type: application/json

{
  "full_name": "Anwar Hossain",
  "email": "anwar@example.com",
  "phone": "+8801712345678",
  "nid": "1234567890123",
  "password": "strongpass1"
}
```
- `200` → `{ "access_token": "...", "expires_in": 3600, "user": { "id", "name", "email", "nid", "phone", "role", "created_at", "updated_at" } }`
- `409` → duplicate email/phone/NID — show the user a friendly “already registered, sign in instead” message.

**`POST /auth/login`**
```http
POST /auth/login
Content-Type: application/json
{ "identifier": "anwar@example.com", "password": "strongpass1" }
```
`identifier` can be email, phone (`+880…` or `01…`), or NID (10 or 13 digits).
- `200` → `TokenResponse` (same shape as register).
- `401` → invalid creds. The server returns a generic `"Invalid credentials"` — never tells you which half was wrong.

**`GET /auth/me`**
- `200` → `UserPublic`.

### 2.2 Reports (citizen)

**`POST /api/report/submit`** — multipart, not JSON
```http
POST /api/report/submit
Authorization: Bearer <token>
Content-Type: multipart/form-data

description        : "Flood water rising…"          (string, 10–4000)
location           : '{"division":"Rangpur","district":"Kurigram",…}'   (JSON-encoded string)
affected_count     : "120"                          (optional string of int)
assistance         : '["rescue_team","shelter"]'    (JSON-encoded string array)
immediate_danger   : "true"                         ("true"/"false")
incident_time      : "within_1h"                    (or omit)
notes              : "Local contact: …"             (or omit)
submitted_at       : "2026-07-03T11:42:00.000Z"    (client clock, audit only)
images             : <binary, one or more>          (image/*, ≤6 MB each, ≤5)
```
- `201` → `ReportOut`.
- `422` → validation failure (description too short, bad incident_time, …). Show the human message in the toast.
- `429` → rate-limited (5 submits per 60 seconds per user). The response carries `Retry-After` in seconds — surface that as a “try again in N s” toast.

**`GET /api/report/{id}`**
- Citizens: only their own reports. Anyone else → `403`.
- Admins: anything.

**`GET /api/report/{id}/images/{filename}`**
- No auth needed; the URL acts as a capability. Returns the image bytes with the correct `Content-Type`.
- `404` if the image is no longer on disk (post-reset demo, accidental `rm`). UI should show a placeholder, not break.

**`GET /api/reports`** — paginated list
- Query params: `bbox=west,south,east,north` (optional), `limit=1..500` (default 100), `offset=0..100000` (default 0).
- Citizens get `{ "items": [...their own...], "count", "total", "offset", "limit" }`.
- Admins get `{ "items": [...all...], ... }`. Always sorted by `created_at` desc.

### 2.3 Reports (admin)

**`PATCH /api/reports/{id}/status`**
```http
PATCH /api/reports/{id}/status
Authorization: Bearer <admin-token>
Content-Type: application/json

{ "status": "resolved", "notes": "Field team confirmed clear" }
```
Allowed `status` values: `pending_ai`, `processed`, `failed`, `resolved`. Only four transitions are permitted (any other pair → `409`):
- `processed → resolved`
- `pending_ai → failed`
- `failed → pending_ai`
- `processed → pending_ai` (triggers a re-run of the AI pipeline)

**`POST /api/admin/reports/{id}/reprocess`**
- Body: none.
- `200` → refreshed `ReportOut`.

### 2.4 Match (relief)

**`POST /api/match/{report_id}?radius_km=25&top_n=3`**
- `radius_km`: `0.5..200` (default 25). `top_n`: `1..10` (default 3).
- `404` if the report doesn’t exist or the caller can’t see it.
- `200` → `MatchResult` with ranked candidates `{ score, distance_km, resource: {...}, reasons: [...] }`.

**`GET /api/match/{report_id}/preview?radius_km=25`** — same payload, `GET`, no commit.

### 2.5 Dashboard (admin)

**`GET /api/dashboard/stats?window_hours=24`**
- `window_hours`: `1..720`. Default 24.
- Returns: `{ window_hours, last_updated, incidents: { total, by_severity, by_status, critical, high, active }, resources: { total, available, in_use, by_type[] }, actions: { pending_dispatch, in_progress, failed } }`.

**`GET /api/dashboard/incidents`**
- Query: `severity=critical|high|medium|low` (omit for all), `status=active|pending_ai|processed|failed|resolved|all` (default `active`), `bbox=…`, `limit`, `offset`.
- Sorted critical-first then newest-first.
- Citizens **do not** have access — they should keep using `/api/reports`.

**`GET /api/dashboard/incidents/{id}`** — single.

**`POST /api/dashboard/incidents/{id}/dispatch`**
```json
{ "resource_ids": ["65fa...", "65fb..."], "notes": "Rescue boat dispatched" }
```
- `400` if no `resource_ids` or none are valid ObjectIds.
- `404` if the incident id is unknown.

**`POST /api/dashboard/incidents/{id}/resolve`**
```json
{ "restore_resources": true, "notes": "All clear" }
```
- `restore_resources` defaults to `true` if omitted. Sets `resolved_at`, stamps `resolved_by`, and flips the last batch of dispatched resources back to `available:true`.

**`GET /api/dashboard/feed?limit=10`**
- One round-trip for the whole dashboard: `{ last_updated, stats, incidents: ReportListOut, resources: ResourceListOut }`. Use this for the polling loop instead of three separate calls.

### 2.6 Geo

**`GET /api/geo/hotspots`** — query params:
- `bbox=west,south,east,north` (recommended; without it the server has to scan everything).
- `grid_size=0.05` (degrees; default 0.05 ≈ 5 km cells).
- `window_hours=24` (default).

Returns `[{ cell: { lat, lng }, count, dominant_severity, dominant_type }]` for the map layer.

### 2.7 Resources

**`GET /api/resources`** — query: `available_only=true|false` (admin default `false`), `limit`.
**`GET /api/resources/{resource_id}`** — one.
**`PATCH /api/resources/{resource_id}/availability`** — admin: `{ "available": false }`.
**`POST /api/resources/reset`** — admin, no body. Resets **all** resources to `available:true`. Demo-only convenience.

### 2.8 Sitreps (admin)

**`POST /api/sitrep/generate`** — body:
```json
{
  "window_hours": 24,
  "divisions": ["Dhaka", "Chattogram"],
  "max_incidents_to_summarize": 25,
  "trigger": "manual"
}
```
**`GET /api/sitrep/latest?divisions=Dhaka&divisions=Chattogram`**
**`GET /api/sitrep?limit=10&divisions=…`**
**`GET /api/sitrep/{sitrep_id}`**
**`GET /api/sitrep/{sitrep_id}/export?format=pdf|text`** — text by default. Streams a file.

---

## 3. Conventions: errors, status codes, content types

### 3.1 Error envelope

Every failure uses this shape via FastAPI's `HTTPException(detail=…)`:
```json
{ "success": false, "error": "Human-readable message", "...extra": "..." }
```
Frontend rule of thumb:
1. `axios` throws on any 4xx/5xx. The body sits on `err.response.data`.
2. The message to show the user is `err.response.data?.error || err.message`. Never show `err.stack`.

### 3.2 Status codes you will actually see

| Status | When | UI behaviour |
|---|---|---|
| `200` / `201` | Success | Render. |
| `400` | Bad input (e.g. `bbox` degenerate, bad resource id). | Inline form error or a banner. |
| `401` | Missing / expired JWT. | Clear token, bounce to `/login`. |
| `403` | Wrong role, or citizen asking for someone else’s report. | “You don’t have access to this report.” |
| `404` | Resource not found / image byte missing / not-yet-generated sitrep. | Empty state component (`EmptyState`). |
| `409` | Illegal status transition or duplicate signup. | Disable the offending action; explain. |
| `422` | Pydantic validation failed (e.g. description too short). | Map `error` to the relevant form field if possible. |
| `429` | Rate-limited (reports submit + login). | Respect `Retry-After`. |
| `500` | AI failed, unhandled crash. | Generic “try again in a moment” toast, log to console. |
| `503` | Mongo not configured. | Show a banner: “API not connected to a database”. |

### 3.3 Content types

- Auth + most request bodies: `application/json`.
- `POST /api/report/submit`: `multipart/form-data` (the only multipart endpoint). Native `FormData` works — set `Content-Type` to `undefined` so the browser sets the boundary.
- `GET /api/sitrep/{id}/export`: `text/plain` or `application/pdf`. Trigger a file download with a hidden `<a download>`.

---

## 4. All edge cases the frontend must handle

This is the list of behaviours that **will** happen during the demo and that the UI must not crash on. Each one points to the endpoint(s) it can come from.

### 4.1 Auth & session

1. **Stale token after server restart** — JWT secret rotates, every previous token is dead.
   *Source:* `get_current_user` (`deps.py`).
   *UI:* A single 401 from any endpoint should clear the cached token (`useAuth().logout`) and redirect to `/login` with a one-time toast “Session expired”.
2. **User logs in as a citizen at `/admin/login`** (or vice versa).
   *Source:* `auth/login`.
   *UI:* After login, check `user.role`. If a citizen arrives at `/admin/dashboard`, bounce them to `/`. If an admin arrives at `/report`, either block the form or just allow it (admin-as-citizen is fine).
3. **Duplicate signup** (email already registered).
   *Source:* `POST /auth/register` → `409`.
   *UI:* Inline “This email is already registered. Sign in instead?” with a one-click flip to the Sign in tab.
4. **Identifier used is a phone that belongs to a different account** vs. **phone not registered**.
   *Source:* `POST /auth/login` → `401`.
   *UI:* Same generic error: “Invalid email/phone/NID or password”. Never reveal that the phone is unknown.
5. **Lost session after a refresh** — token cleared from `localStorage` by the user.
   *Source:* session bootstrap.
   *UI:* On mount, call `/auth/me` once. If it 401s, treat as logged out. Don’t show a flash of the logged-in state.

### 4.2 Report submission

6. **Description too short** after trim.
   *Source:* `POST /api/report/submit` → `422` with message.
   *UI:* Server is the source of truth, but the form already disables submit when `description.trim().length < 10`. Show the server’s message if you somehow bypass the client check.
7. **`division` changed by the user mid-flight while district no longer belongs to it**.
   *Source:* client-driven inconsistency.
   *UI:* On change of `division`, reset `district` and `upazila`. If the user submits without a valid (server-recognized) `division`, show 422.
8. **Image too big or wrong mime**.
   *Source:* dropzone already caps at 6 MB / `image/*`. The backend also enforces image MIME via storage helpers.
   *UI:* If the backend rejects an image (`error: "File type not allowed"`), drop just that file from `FormData` and toast the user. Don't kill the whole submit.
9. **Network drop mid-upload**.
   *Source:* axios.
   *UI:* Use the `onUploadProgress` callback to show a thin progress bar. On fail, retry once after 1.5 s with exponential backoff (max 2 retries). After that, surface “Submission failed — retry?” with the prior payload still in state.
10. **Double-tap submit button**.
    *Source:* `POST /api/report/submit` rate-limit + dedupe (`REPORT_RL_MAX=5` per 60 s, dedupe window 30 s).
    *UI:* Disable the button the moment the request fires. If the user *does* double-tap and gets back a 429, show “Whoa, too many submissions — wait N seconds”. The dedupe window means an identical payload returns the same report id, which is **safe** — the UI can ignore duplicates.
11. **AI pipeline marks the report `failed`** (OpenAI down or malformed response).
    *Source:* `ReportOut.status === "failed"` + `ReportOut.error`.
    *UI:* Show a banner on the success page: “Saved — but our AI had a hiccup. A human will review shortly.” The report is still persisted, so the user can be confident it isn’t lost.
12. **AI returns a low-confidence result** (`ai_output.combined.confidence < 0.4`).
    *Source:* same as above.
    *UI:* Tag the preview card with a low-confidence badge; mention that admins will verify.
13. **Report status changes after submit**.
    *Source:* background AI pipeline.
    *UI:* On the success screen, return `status: "pending_ai"`. If the UI later navigates to detail and finds `status: "processed"`, render the AI block. Don't poll from the success screen — the dashboard polls `/api/dashboard/feed`.

### 4.3 Listing & filtering

14. **Empty result set** (e.g. “no reports in this division yet”).
    *Source:* `GET /api/reports` → `{ items: [], total: 0, count: 0 }`.
    *UI:* Render the `EmptyState` component. Don’t silently render nothing.
15. **Pagination beyond the end**.
    *Source:* `GET /api/reports?offset=10000`.
    *UI:* Honour `total`: clamp the next-page button or use `total - offset` to detect the last page.
16. **`bbox` from the live map is degenerate** (the user zoomed all the way in).
    *Source:* client-side bug.
    *UI:* Client-side guard: only send `bbox` when all four numbers are finite and `west < east && south < north`.
17. **Search by `query` (text) is not yet a server-side param** — the current backend accepts `limit`/`offset`/`bbox` but not a free-text filter.
    *UI:* Either keep filtering client-side over the page slice (current behaviour in `useReportsList.js`), or call the AI later. Don’t pretend the server is doing it.

### 4.4 Images & media

18. **Image URL points to a missing file**.
    *Source:* `GET /api/report/{id}/images/{filename}` → `404`.
    *UI:* `<img onError={() => setBroken(true)} />` + a placeholder icon.
19. **CORS block on image fetch** (different host in prod).
    *Source:* browser-side.
    *UI:* Backend already sets `CORSMiddleware` with `allow_origins` from env. If something still trips, log the actual origin mismatch and add it to `cors_origins_list` in `core/config.py`.

### 4.5 Admin dashboard

20. **Incident race**: two admins try to dispatch the same resources.
    *Source:* `POST /api/dashboard/incidents/{id}/dispatch`.
    *UI:* Refresh the resource availability after dispatch and disable buttons whose resources are now `available:false`. Server is idempotent on the underlying `update_many` — calling twice just re-marks them.
21. **Resolve called before dispatch** (nothing to restore).
    *Source:* server returns `200` with `resources_restored: 0`.
    *UI:* Still show success, just don’t claim “we freed up resources”.
22. **Status transition outside the allowed set**.
    *Source:* `PATCH /api/reports/{id}/status` → `409`.
    *UI:* The response includes `allowed_transitions_from_current` in `detail` — render only those buttons. Hide the rest.
23. **Reprocess after AI was already in `pending_ai`** (nothing to do).
    *Source:* `POST /api/admin/reports/{id}/reprocess` → either 200 with the same doc, or fresh output.
    *UI:* Show a spinner while waiting; the response is the source of truth.
24. **`/api/dashboard/feed` polling storms**.
    *Source:* client bug.
    *UI:* The contract is 5–10 s intervals. Cap at 1 call per 4 s, pause polling when the tab is `document.hidden`, resume on `visibilitychange === 'visible'`.
25. **`last_updated` hasn’t changed in N polls** → don’t re-render the top tiles. Cheap optimization.

### 4.6 Geo / map

26. **Hotspots endpoint returns 200 but the `bbox` was missing or invalid**.
    *Source:* server returns `[]` (no filter → no I/O cost wall but also no useful answer for a huge country).
    *UI:* Always send `bbox` from the visible map viewport.
27. **Cell with `count > 0` but no `dominant_severity`** (the cell aggregates only `pending_ai` failures).
    *UI:* Default the marker color to `medium`, not `unknown`.

### 4.7 Sitrep

28. **No sitrep generated yet**.
    *Source:* `GET /api/sitrep/latest` → `404`.
    *UI:* Show “Generating first briefing…” and silently retry every 30 s (the 1-hour auto-tick will fill it in).
29. **`/api/sitrep/{id}/export?format=pdf` returns 500** if the PDF path is broken on the server.
    *UI:* Fallback to `format=text` automatically.

### 4.8 Network / infra

30. **CORS preflight fails** because the frontend origin isn’t in `cors_origins_list`.
    *Source:* `CORSMiddleware` config in `app/main.py`.
    *UI:* A console `AxiosError: Network Error` with no response body. Backend fix is one env var; document the origin and add it.
31. **Mongo is not configured** (`backend/.env` missing `MONGODB_URI`).
    *Source:* every endpoint that hits a DB returns `503`.
    *UI:* Treat as a fatal startup problem; show the “API not connected” banner instead of the dashboard.
32. **Token in `localStorage` becomes invalid** while a long-polling tab is open.
    *Source:* §4.1.
    *UI:* Detect on next polling response, stop polling, redirect.

---

## 5. Safely establishing the connection from the frontend

These are the steps a frontend dev (or this assistant on a future turn) should follow to wire `frontend/src/services/api.js` to the real backend without breaking the mock.

### 5.1 In `frontend/.env` (or `.env.local`)

```bash
# When this is "false", the service layer stops using mockData.js.
VITE_USE_MOCK=false

# Where the backend lives. Local dev default is shown; staging/prod
# are different env files.
VITE_API_BASE_URL=http://localhost:8000
```

Do **not** commit a production URL to the repo. Use a `.env.example` instead.

### 5.2 In `frontend/src/services/api.js`

The file already has:
```js
const USE_MOCK =
  import.meta?.env?.VITE_USE_MOCK === undefined
    ? true
    : String(import.meta.env.VITE_USE_MOCK).toLowerCase() !== 'false';
```
This is the right toggle. When `VITE_USE_MOCK=false`, the `if (USE_MOCK)` branches in `reportsApi` / `dashboardApi` skip and the real axios calls run. Add the new endpoints behind the same flag — never delete the mock until the UI has been validated end-to-end on real data.

### 5.3 Set up an axios instance with auth + error plumbing

Replace the bare `axios.create({...})` with a configured one. Keep it in `services/api.js` so the whole app inherits the behaviour:
```js
import axios from 'axios';

const TOKEN_KEY = 'rg_access_token';

export const apiClient = axios.create({
  baseURL: import.meta?.env?.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 15000,
});

// Attach the JWT to every request automatically.
apiClient.interceptors.request.use((cfg) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  // multipart uploads must not force a Content-Type — let the browser
  // set the boundary header itself.
  if (cfg.data instanceof FormData) {
    delete cfg.headers['Content-Type'];
  }
  return cfg;
});

// On 401, drop the token so the rest of the app can route to /login.
apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      // Defer navigation to a route guard; setting window.location here
      // would interrupt in-flight requests unpredictably.
      window.dispatchEvent(new CustomEvent('rg:auth:expired'));
    }
    return Promise.reject(err);
  },
);
```

### 5.4 Token storage + login

`UserAuthContext.jsx` and `AdminLogin.jsx` currently use a stub. Replace with:
1. On register/login success → `localStorage.setItem(TOKEN_KEY, response.access_token)`.
2. Stash `response.user` in React state (or another localStorage key).
3. On boot → if `TOKEN_KEY` exists, fire `GET /auth/me` once and rehydrate `user`.
4. On logout → `localStorage.removeItem(TOKEN_KEY)` and reset state.

This keeps backwards compatibility with the existing UI keys (`rg_user_session_v1`, `rg_admin_auth`) — those can remain as “UI-side flags” that just gate routing, not auth.

### 5.5 Calling endpoints for the first time — the safe order

Do this in order; do not skip ahead. Each step ends with a manual verification.

1. **Health ping.** Open `http://localhost:8000/health` in the browser. You should see `{"status":"ok","mongo":"ok"}`. If `mongo` is `not_configured`, the backend is up but no DB is wired — every endpoint will 503.
2. **Auth round-trip.** From a JS console:
   ```js
   const { data } = await fetch('http://localhost:8000/auth/login', {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({ identifier: 'admin@reliefgrid', password: '<seeded-admin-password>' })
   }).then(r => r.json());
   console.log(data.access_token);
   ```
   Replace the password with whatever `backend/scripts/seed_admin.py` wrote. If you get a token, the JWT path is alive end-to-end.
3. **Submit a test report (multipart).** Use the React form — it already builds the right `FormData`. Hit submit, expect a `201` with a non-empty `id`. If you get `422`, read the `error` and update the form.
4. **Read it back.** `GET /api/reports/{id}` with the same token should return the same shape. The dashboard list (`GET /api/reports`) should now contain it.
5. **Wait for the AI pipeline.** Within ~10 s the document’s `status` becomes `processed` and `ai_output.combined` is populated. Polling `/api/reports/{id}` is the simplest verification.
6. **Switch `VITE_USE_MOCK=false`** in `.env.local` and restart Vite. From this point the React UI hits the real backend.

### 5.6 CORS sanity (do this before any of the steps above once you’ve touched origins)

If the frontend is on a different origin (e.g. `:5173`) the browser will preflight every non-GET request. Verify with:
```bash
curl -i -X OPTIONS http://localhost:8000/auth/login \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```
You should see `Access-Control-Allow-Origin: http://localhost:5173`. The backend’s `cors_origins_list` (in `core/config.py`, fed by env) must include it. Add origins via the env, never in code.

### 5.7 The shape the frontend should expect

Three rules so nothing breaks:

- **Always read `data.items` / `data.user` / `data.access_token` on a 200/201.** The error path uses `err.response.data.error`.
- **Treat every field marked `Optional` in `app/schemas/*` as missing-or-null.** Use `report?.ai_output?.combined?.severity` style optional chains, never direct property access.
- **Never trust `submitted_at` from the client.** Backend stamps `created_at`. Anything that orders reports should sort by `created_at` (desc) — `services/api.js` already does `b.submittedAt - a.submittedAt` for the mock; switch the comparison to `created_at` when real data arrives.

---

## 6. Troubleshooting checklist

When something looks wrong, walk this list top-to-bottom.

1. **`/health` works but every other call 503s** → `MONGODB_URI` is unset or the cluster is unreachable.
2. **`/health` errors with `error: <message>`** → backend can’t even reach Mongo. Check credentials / IP allowlist on Atlas.
3. **Login returns `401` but you’re sure the password is right** → identifier is being normalized differently (e.g. an extra space, a `+880` vs `01…` mismatch). Use the exact form they signed up with.
4. **`/api/report/submit` returns `422` and the form looks fine** → at least one of `description/location/assistance/incident_time` is sending a value the server didn’t expect. The error string usually names the field.
5. **`/api/report/submit` returns `413`/timeout** → image is too large; the dropzone cap is 6 MB but a raw `FormData` bypass can slip through.
6. **`/api/dashboard/*` returns `403`** → the cached token is a citizen role. Sign out and sign back in with an admin seed account.
7. **CORS preflight returns the wrong `Access-Control-Allow-Origin`** → add the frontend origin to `cors_origins_list` (env var), then restart uvicorn.
8. **OpenAI-related failures (`status: "failed"` on report)** → backend logs the error in `app/services/report.py`. The report is still saved — admins can fix it via `PATCH /api/reports/{id}/status` and `POST /api/admin/reports/{id}/reprocess`.
9. **`/api/sitrep/latest` is `404` after a fresh server start** → the 1-hour auto-tick hasn’t run yet. Manually `POST /api/sitrep/generate` once for the demo.
10. **Token works for `/auth/me` but not for `/api/reports`** → JWT decoded but `user_id` doesn’t exist in Mongo (server-restart between token issue and check). Sign in again.

---

*If you add a new endpoint, update §1, §2, and any new edge-case bullets in §4 — the document is the contract.*
