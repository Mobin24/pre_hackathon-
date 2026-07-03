# DRRCS Backend API — Auth Contract (v1)

> This document is the **frontend contract** for the DRRCS backend authentication API.
> It defines request/response shapes, status codes, error handling, CORS, and the JWT flow.
> Always check `expires_in` to know when to refresh. Do **not** parse or trust the token payload client-side — call `/auth/me` instead.

**Base URL (local dev):** `http://127.0.0.1:8000`
**API version prefix:** `/auth`
**OpenAPI / Swagger UI:** `http://127.0.0.1:8000/docs`

---

## 1. Conventions

### JSON only
All requests and responses are JSON. Set `Content-Type: application/json`.

### IDs
User IDs are strings — MongoDB `ObjectId` serialized to hex (24 chars). Treat them as opaque.

### Timestamps
ISO-8601 strings with timezone offset, e.g. `"2026-07-03T11:04:55.754470+00:00"`.

### Error shape
FastAPI's standard envelope:
```json
{ "detail": "Email already registered" }
```
For validation errors (422), `detail` is an array:
```json
{
  "detail": [
    { "loc": ["body", "email"], "msg": "value is not a valid email address", "type": "value_error" }
  ]
}
```

### Status codes you'll see

| Code | Meaning | When |
|---|---|---|
| `200` | OK | Successful read or login |
| `201` | Created | Successful register |
| `401` | Unauthorized | Missing token, bad signature, expired token, wrong password |
| `403` | Forbidden | Token is valid but role doesn't match |
| `409` | Conflict | Email already registered |
| `422` | Unprocessable Entity | Validation failed (bad email, short password, etc.) |
| `503` | Service Unavailable | MongoDB not configured on the server |

### CORS
Backend allows `CORS_ORIGINS` from `.env` (default `http://localhost:5173`).
Credentials (`Authorization` header) are allowed. Cookies/sessions are **not** used — JWT only.

---

## 2. Endpoints

### 2.1 `POST /auth/register`

Create a new user account and immediately return a signed access token.

**Request body**
```json
{
  "name": "Alice",
  "email": "alice@example.com",
  "password": "goodpass1",
  "role": "citizen"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | 1–100 chars, trimmed server-side |
| `email` | string | yes | RFC-compliant email, lowercased on save |
| `password` | string | yes | 8–128 chars |
| `role` | `"citizen"` \| `"admin"` | no | Defaults to `"citizen"`. Production typically rejects `"admin"` self-assignment — current MVP allows it. |

**Success — `201 Created`**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": "6a4797572ab462cfec9ead03",
    "name": "Alice",
    "email": "alice@example.com",
    "role": "citizen",
    "created_at": "2026-07-03T11:04:55.754470+00:00",
    "updated_at": "2026-07-03T11:04:55.754470+00:00"
  }
}
```

**Errors**
- `409 Conflict` — `{"detail":"Email already registered"}`
- `422` — validation (bad email / short password / name too long)
- `503` — Mongo not configured (backend offline)

**Frontend implications**
- Persist `access_token` (e.g. `localStorage` or in-memory) and the `user` object.
- Decode `expires_in` (seconds) once to know when to force re-auth.
- Do **not** trust the `role` field for routing until you also call `/auth/me` on app load — the role could have changed since issue.

---

### 2.2 `POST /auth/login`

Authenticate with email + password.

**Request body**
```json
{ "email": "alice@example.com", "password": "goodpass1" }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `email` | string | yes | Looked up lowercased |
| `password` | string | yes | At least 1 char (the hash check enforces actual strength) |

**Success — `200 OK`**

Same `TokenResponse` shape as `/auth/register`:
```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": { "id": "...", "name": "...", "email": "...", "role": "citizen", "created_at": "...", "updated_at": "..." }
}
```

**Errors**
- `401 Unauthorized` — `{"detail":"Invalid email or password"}` (intentionally vague — same response for unknown email vs. wrong password, to prevent enumeration)

**Frontend implications**
- Single error message — show "Invalid email or password" for both cases.
- On success, replace any existing stored token.

---

### 2.3 `GET /auth/me`

Return the current user's profile using the bearer token.

**Headers**
```
Authorization: Bearer <access_token>
```

**Success — `200 OK`**
```json
{
  "id": "6a4797572ab462cfec9ead03",
  "name": "Alice",
  "email": "alice@example.com",
  "role": "citizen",
  "created_at": "2026-07-03T11:04:55.754470+00:00",
  "updated_at": "2026-07-03T11:04:55.754470+00:00"
}
```

**Errors**
- `401 Unauthorized` with one of:
  - `{"detail":"Not authenticated"}` — no `Authorization` header
  - `{"detail":"Invalid or expired token"}` — bad signature / expired / malformed
  - `{"detail":"User no longer exists"}` — token is valid but the user was deleted

**Frontend implications**
- Use this on app load to validate a stored token and refresh user state.
- Do **not** trust `localStorage` blindly — token could be expired or revoked (user deleted).

---

## 3. JWT details (for reference only)

- **Algorithm:** `HS256`
- **Lifetime:** `TOKEN_EXPIRY_MINUTES` from backend `.env` (default `1440` = 24h)
- **Payload claims:**
  ```json
  { "sub": "<user_id>", "role": "citizen|admin", "iat": <unix>, "exp": <unix> }
  ```
- **Header value:** `Authorization: Bearer <token>`

> ⚠️ **Don't decode the JWT client-side for authorization decisions.** The token's role can be revoked server-side. Always re-check via `/auth/me` or a role-gated endpoint.

---

## 4. TypeScript-style shapes (copy-paste into `frontend/src/services/api.ts`)

```ts
export type Role = "citizen" | "admin";

export interface UserPublic {
  id: string;
  name: string;
  email: string;
  role: Role;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;     // seconds
  user: UserPublic;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  role?: Role;            // defaults to "citizen"
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface ApiError {
  detail: string | Array<{ loc: (string | number)[]; msg: string; type: string }>;
}

export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
```

---

## 5. Minimal frontend helper (reference)

```ts
async function authFetch<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const err: ApiError = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiHttpError(res.status, err);
  }
  return res.json() as Promise<T>;
}

export class ApiHttpError extends Error {
  constructor(public status: number, public body: ApiError) {
    super(typeof body.detail === "string" ? body.detail : "Request failed");
  }
}
```

---

## 6. End-to-end flow

```
1. User signs up           → POST /auth/register      → store { token, user }
2. User signs in later     → POST /auth/login         → store { token, user }
3. User reloads the app    → GET  /auth/me            → if 401, force re-login
4. Token expires           → next protected call returns 401
                              → frontend: clear stored token, redirect to /login
5. Admin-only screens      → POST/PUT/DELETE endpoints with `Depends(require_role("admin"))`
                              will return 403 with `{"detail":"Requires role: admin"}`
                              if a citizen's token is presented.
```

---

## 7. Versioning & stability

- This contract corresponds to **backend Phase 2 (Auth)**. Other endpoints (`/api/report/...`) are documented separately.
- Any breaking change (renaming fields, switching to refresh tokens, changing `expires_in`) will bump the API version prefix.
