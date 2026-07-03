"""End-to-end smoke for the gap closures added in the last pass.

Covers:
- Gap #1: PATCH /api/reports/{id}/status (allowed + 400 + 409 transitions)
- Gap #3: GET /api/resources?type= guard (invalid → 422)
- Gap #4: rate-limit (6th submit → 429) + dedupe (same payload → same id)
- Gap #5: pagination metadata (offset/total/limit) on /reports, /resources,
  /dashboard/incidents.

Runs against mongomock-motor + httpx ASGI transport; no real Mongo or
OpenAI calls required.
"""
import asyncio
import io
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

# Must be set BEFORE the app loads so is_configured() is True.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")
os.environ.setdefault("AI_RECOVERY_THRESHOLD_SECONDS", "1")

import httpx
from mongomock_motor import AsyncMongoMockClient

import app.core.db as db_mod
import app.models.user as user_model
from app.core.security import hash_password
from app.main import app
from app.models import report as report_model
from app.models import resource as resource_model
from app.routes import report as report_routes

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa3\x9c\xb1\x00"
    b"\x00\x00\x00IEND\xaeB`\x82"
)


# --- canned LLM response ----------------------------------------------------
TEXT_OK: Dict[str, Any] = {
    "type": "flood",
    "severity": "high",
    "urgency_score": 78,
    "assistance_detected": ["rescue_team", "water"],
    "summary": "Flooding reported in Sylhet.",
    "confidence": 0.9,
    "language": "en",
    "raw_signal": {"keywords": ["flood"], "tone": "urgent"},
}


def fake_chat_json():
    async def _impl(*, model: str, messages, **kwargs):
        return TEXT_OK
    return _impl


# --- helpers ----------------------------------------------------------------
async def register(client: httpx.AsyncClient, email: str, name: str) -> str:
    r = await client.post(
        "/auth/register",
        json={"full_name": name, "email": email, "password": "goodpass1"},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


async def login(client: httpx.AsyncClient, identifier: str, password: str) -> str:
    r = await client.post("/auth/login", json={"identifier": identifier, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def seed_admin(email: str = "admin@example.com", password: str = "adminpass1") -> None:
    await db_mod._db[user_model.COLLECTION].insert_one(
        {
            "name": "Admin",
            "email": email,
            "password_hash": hash_password(password),
            "role": "admin",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )


def submit_form(token: str, description: str, *, location_div: str = "Sylhet") -> Dict[str, Any]:
    return {
        "data": {
            "description": description,
            "location": str(
                {"division": location_div, "coords": {"lat": 24.89, "lng": 91.87}}
            ).replace("'", '"'),
            "affected_count": "5",
            "assistance": '["rescue_team", "water"]',
            "immediate_danger": "true",
            "incident_time": "within_1h",
        },
        "headers": {"Authorization": f"Bearer {token}"},
    }


async def wait_for_status(
    client: httpx.AsyncClient, token: str, report_id: str, target: str, timeout_s: float = 5.0
) -> Dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + timeout_s
    last: Dict[str, Any] = {}
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get(
            f"/api/report/{report_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        last = r.json()
        if last.get("status") == target:
            return last
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target}, got {last.get('status')}")


def reset_module_state() -> None:
    """Wipe the in-memory rate-limit/dedupe dicts between phases."""
    report_routes._rate_log.clear()
    report_routes._dedupe_cache.clear()


# --- main -------------------------------------------------------------------
async def main() -> None:
    mock_client = AsyncMongoMockClient()
    db_mod._client = mock_client
    db_mod._db = mock_client["drrcs_test_gaps"]

    try:
        await user_model.ensure_indexes()
        await report_model.ensure_indexes()
        await resource_model.ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        print("index note:", exc)

    # Patch AI to a fake chat_json so the background pipeline finishes fast.
    import app.ml.ai_pipeline as _pl
    _real = _pl.chat_json
    _pl.chat_json = fake_chat_json()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:

        # ----------------------------------------------------------------
        # GAP #4a — rate limit (5 per minute → 6th hits 429)
        # ----------------------------------------------------------------
        token_rl = await register(client, "rl_alice@example.com", "RL Alice")
        reset_module_state()
        last_codes: List[int] = []
        for i in range(6):
            # Vary the description slightly to dodge dedupe, but keep one
            # that's identical between i=2 and i=3 to test dedupe separately.
            payload = submit_form(token_rl, f"flood description #{i} {os.urandom(2).hex()}")
            r = await client.post(
                "/api/report/submit", data=payload["data"], headers=payload["headers"]
            )
            last_codes.append(r.status_code)
        print("RATE_LIMIT_CODES", last_codes)
        # The first 5 should be 201; the 6th must be 429.
        assert last_codes[:5] == [201, 201, 201, 201, 201], last_codes
        assert last_codes[5] == 429, last_codes
        # 429 carries a Retry-After header.
        r6 = await client.post(
            "/api/report/submit",
            data=submit_form(token_rl, "another one")["data"],
            headers=submit_form(token_rl, "another one")["headers"],
        )
        assert "retry-after" in {k.lower() for k in r6.headers.keys()}, r6.headers

        # ----------------------------------------------------------------
        # GAP #4b — dedupe (same payload within 30s returns existing id)
        # ----------------------------------------------------------------
        token_dd = await register(client, "dd_bob@example.com", "DD Bob")
        reset_module_state()
        payload_dd = submit_form(token_dd, "Identical flood report text")
        r1 = await client.post(
            "/api/report/submit", data=payload_dd["data"], headers=payload_dd["headers"]
        )
        assert r1.status_code == 201, r1.text
        id_1 = r1.json()["id"]
        r2 = await client.post(
            "/api/report/submit", data=payload_dd["data"], headers=payload_dd["headers"]
        )
        # Dedupe returns the original doc. Status is 201 (idempotent retry,
        # same body), but the response body must carry the same `id` as r1
        # — that's what proves we did NOT double-write to Mongo.
        print("DEDUPE_CODES", r1.status_code, r2.status_code, r2.json().get("id") == id_1)
        assert r2.status_code in (200, 201), r2.text
        assert r2.json()["id"] == id_1
        # And only one Mongo doc should exist with that description (dedupe proves
# we did not double-write). Note: the doc stores user_id as ObjectId in
# Mongo, so we filter on description only.
        from bson import ObjectId
        from app.core.db import get_database
        col = get_database()[report_model.COLLECTION]
        docs = await col.find(
            {"description": "Identical flood report text"}
        ).to_list(length=10)
        print("MONGO_MATCHING", len(docs))
        assert len(docs) == 1, f"expected 1 mongo doc, got {len(docs)}"

        # ----------------------------------------------------------------
        # GAP #3 — /resources?type= guard (invalid → 422)
        # ----------------------------------------------------------------
        await seed_admin()
        admin_token = await login(client, "admin@example.com", "adminpass1")
        # Seed a couple of resources so the OK path has something to return.
        await db_mod._db[resource_model.COLLECTION].insert_many(
            [
                {
                    "code": "TEST-AMB-001",
                    "type": "ambulance",
                    "name": "Test Ambulance",
                    "assistance": ["ambulance", "medicine"],
                    "skills": [],
                    "location": {"division": "Dhaka", "coords": {"lat": 23.73, "lng": 90.40}},
                    "capacity": 1,
                    "available": True,
                    "contact": {},
                    "priority": 0,
                    "tags": [],
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                },
                {
                    "code": "TEST-SHELTER-001",
                    "type": "shelter",
                    "name": "Test Shelter",
                    "assistance": ["shelter"],
                    "skills": [],
                    "location": {"division": "Dhaka", "coords": {"lat": 23.74, "lng": 90.41}},
                    "capacity_total": 100,
                    "capacity_used": 0,
                    "capacity": 1,
                    "available": True,
                    "contact": {},
                    "priority": 0,
                    "tags": [],
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                },
            ]
        )
        r_ok = await client.get(
            "/api/resources?type=ambulance",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print("RESOURCE_OK", r_ok.status_code, "count=", r_ok.json().get("count"))
        assert r_ok.status_code == 200, r_ok.text
        assert r_ok.json()["count"] == 1

        r_bad = await client.get(
            "/api/resources?type=helicopter",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print("RESOURCE_BAD_TYPE", r_bad.status_code)
        assert r_bad.status_code == 422, r_bad.text

        # ----------------------------------------------------------------
        # GAP #5a — pagination on /resources (offset + total)
        # ----------------------------------------------------------------
        r_pag = await client.get(
            "/api/resources?limit=1&offset=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print("RESOURCE_PAG", r_pag.status_code, r_pag.json().keys())
        body = r_pag.json()
        assert r_pag.status_code == 200, r_pag.text
        assert body["total"] == 2
        assert body["offset"] == 1
        assert body["limit"] == 1
        assert body["count"] == 1

        # ----------------------------------------------------------------
        # GAP #5b — pagination on /reports (citizen scope + offset)
        # ----------------------------------------------------------------
        token_l = await register(client, "pag_carol@example.com", "Pag Carol")
        reset_module_state()
        ids: List[str] = []
        for i in range(3):
            payload = submit_form(token_l, f"unique-flood-text-{i}-{os.urandom(3).hex()}")
            r = await client.post(
                "/api/report/submit", data=payload["data"], headers=payload["headers"]
            )
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
        # wait for the AI pipeline to settle so status doesn't change between
        # list calls (cosmetic, not required).
        for rid in ids:
            await wait_for_status(client, token_l, rid, "processed", timeout_s=5.0)
        r_list = await client.get(
            "/api/reports?limit=2&offset=0",
            headers={"Authorization": f"Bearer {token_l}"},
        )
        print("REPORT_LIST", r_list.status_code, r_list.json().keys())
        body = r_list.json()
        assert r_list.status_code == 200, r_list.text
        assert body["total"] == 3
        assert body["offset"] == 0
        assert body["limit"] == 2
        assert body["count"] == 2

        r_list2 = await client.get(
            "/api/reports?limit=2&offset=2",
            headers={"Authorization": f"Bearer {token_l}"},
        )
        assert r_list2.json()["count"] == 1

        # ----------------------------------------------------------------
        # GAP #5c — pagination on /dashboard/incidents
        # ----------------------------------------------------------------
        r_inc = await client.get(
            "/api/dashboard/incidents?limit=2&offset=0",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print("INCIDENTS", r_inc.status_code, r_inc.json().keys())
        body = r_inc.json()
        assert r_inc.status_code == 200, r_inc.text
        assert body["limit"] == 2
        assert body["offset"] == 0
        assert body["count"] <= 2
        assert body["total"] >= 1  # admin sees everyone's

        # ----------------------------------------------------------------
        # GAP #1 — PATCH /api/reports/{id}/status
        # ----------------------------------------------------------------
        rid = ids[0]
        # 1. Move processed → resolved.
        r_patch = await client.patch(
            f"/api/reports/{rid}/status",
            json={"status": "resolved", "notes": "handled by FD"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print("PATCH_RESOLVED", r_patch.status_code)
        assert r_patch.status_code == 200, r_patch.text
        assert r_patch.json()["status"] == "resolved"

        # 2. Already-resolved → same status = 400.
        r_same = await client.patch(
            f"/api/reports/{rid}/status",
            json={"status": "resolved"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print("PATCH_SAME", r_same.status_code)
        assert r_same.status_code == 400, r_same.text

        # 3. Invalid target status = 422.
        r_bad_status = await client.patch(
            f"/api/reports/{rid}/status",
            json={"status": "alien"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print("PATCH_BAD", r_bad_status.status_code)
        assert r_bad_status.status_code == 422, r_bad_status.text

        # 4. resolved → failed is NOT in ALLOWED_TRANSITIONS → 409.
        r_forbid = await client.patch(
            f"/api/reports/{rid}/status",
            json={"status": "failed"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print("PATCH_409", r_forbid.status_code, r_forbid.json())
        assert r_forbid.status_code == 409, r_forbid.text
        assert "allowed_transitions_from_current" in r_forbid.json()["detail"]

        # 5. processed → pending_ai (reprocess path).
        # First pick a fresh, processed report.
        rid2 = ids[1]
        r_proc = await client.patch(
            f"/api/reports/{rid2}/status",
            json={"status": "pending_ai", "notes": "force re-run"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print("PATCH_REPROCESS", r_proc.status_code, r_proc.json().get("status"))
        assert r_proc.status_code == 200, r_proc.text
        # Auto-reprocess awaits the pipeline (admin route) → processed.
        # (Our fake chat_json returns synchronously; should be fast.)
        assert r_proc.json()["status"] in ("processed", "pending_ai")
        if r_proc.json()["status"] == "pending_ai":
            # give the background sweep a moment
            await wait_for_status(client, admin_token, rid2, "processed", timeout_s=3.0)

        # 6. Citizen cannot PATCH.
        r_cit = await client.patch(
            f"/api/reports/{rid2}/status",
            json={"status": "resolved"},
            headers={"Authorization": f"Bearer {token_l}"},
        )
        print("PATCH_CITIZEN", r_cit.status_code)
        assert r_cit.status_code == 403, r_cit.text

        # 7. Unknown id → 404.
        r_404 = await client.patch(
            "/api/reports/000000000000000000000000/status",
            json={"status": "resolved"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print("PATCH_404", r_404.status_code)
        assert r_404.status_code == 404, r_404.text

    _pl.chat_json = _real
    print("\nALL GAP-CLOSURE ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())