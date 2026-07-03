"""End-to-end smoke test for the geo-intelligence endpoints.

Covers:
- GET /api/reports?bbox=...    (returns only reports inside the rectangle)
- GET /api/reports?bbox=...    with malformed input  → 400
- GET /api/reports?bbox=...    with empty range      → 400
- GET /api/geo/hotspots        admin only            → 403 for citizen
- GET /api/geo/hotspots        dense cell produces a hotspot
- GET /api/geo/hotspots        isolated reports do not count
- GET /api/geo/hotspots        critical+worse severity ranks above high
- Backward compatibility: GET /api/reports without bbox returns all

We bypass the AI pipeline entirely by writing docs directly into Mongo with
handcrafted `ai_output.combined` values. This isolates the geo code from
the LLM code.

We bypass `/auth/register` for the admin (which hardcodes role='citizen') by
seeding the admin user directly in Mongo, then logging in normally.
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

import httpx
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

import app.core.db as db_mod
import app.models.user as user_model
from app.core.security import hash_password
from app.main import app
from app.models.report import COLLECTION, REPORT_STATUS_PROCESSED


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_report_doc(
    *,
    user_id: ObjectId,
    lat: float,
    lng: float,
    severity: str = "high",
    urgency: int = 80,
    disaster_type: str = "flood",
    created_at: datetime | None = None,
) -> Dict[str, Any]:
    """Build a fully-formed report doc that matches what the AI pipeline
    would have produced. We skip the actual pipeline to isolate the geo
    code from the LLM code.
    """
    now = created_at or _utcnow()
    return {
        "_id": ObjectId(),
        "user_id": user_id,
        "description": "Test report for geo smoke test.",
        "location": {
            "division": "Sylhet",
            "district": "Sunamganj",
            "upazila": None,
            "area": None,
            "coords": {"lat": lat, "lng": lng},
        },
        "affected_count": None,
        "assistance": [],
        "immediate_danger": False,
        "incident_time": None,
        "notes": None,
        "images": [],
        "submitted_at_client": None,
        "status": REPORT_STATUS_PROCESSED,
        "ai_output": {
            "combined": {
                "type": disaster_type,
                "severity": severity,
                "urgency_score": urgency,
                "summary": "smoke test",
                "recommendation": "smoke test",
                "assistance_needed": [],
                "confidence": 0.8,
            },
            "text": None,
            "image": None,
            "models": {"text": "gpt-4o-mini", "vision": None},
            "generated_at": now.isoformat(),
        },
        "error": None,
        "created_at": now,
        "updated_at": now,
    }


async def main() -> None:
    mock_client = AsyncMongoMockClient()
    db_mod._client = mock_client
    db_mod._db = mock_client["drrcs_test"]

    try:
        await user_model.ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        print("index note:", exc)

    db = db_mod._db

    # --- Seed an admin user directly in Mongo (HTTP /auth/register is citizen-only).
    admin_user_doc = {
        "_id": ObjectId(),
        "name": "Admin Geo",
        "email": "admingeo@example.com",
        "password_hash": hash_password("goodpass1"),
        "role": "admin",
        "nid": None,
        "phone": None,
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
    }
    await db["users"].insert_one(admin_user_doc)
    admin_uid = admin_user_doc["_id"]

    # --- Seed a citizen user (we'll also seed reports under this uid
    #     so the bbox test exercises the admin-sees-all path with real data).
    citizen_uid = ObjectId()

    # 12 reports in a tight Sylhet cell.
    sylhet_docs: List[Dict[str, Any]] = []
    for i in range(12):
        doc = _make_report_doc(
            user_id=admin_uid,            # admin owns these — admin can see all
            lat=24.85 + 0.001 * (i % 3),  # 24.850..24.852
            lng=91.40 + 0.001 * (i // 3), # 91.400..91.403
            severity="high" if i < 8 else "critical",
            urgency=80 + i,
            disaster_type="flood",
        )
        sylhet_docs.append(doc)
    await db[COLLECTION].insert_many(sylhet_docs)

    # 5 isolated reports elsewhere — should NOT form a hotspot.
    # Note: chosen so each is in its OWN cell (far enough from each other
    # AND from the Dhaka cell we'll add later for the ranking test).
    isolated: List[Dict[str, Any]] = [
        _make_report_doc(user_id=admin_uid, lat=22.10, lng=92.10, urgency=70),  # Chittagong
        _make_report_doc(user_id=admin_uid, lat=22.80, lng=91.80, urgency=60),  # Noakhali
        _make_report_doc(user_id=admin_uid, lat=25.10, lng=88.70, urgency=65),  # Dinajpur
        _make_report_doc(user_id=admin_uid, lat=25.50, lng=89.50, urgency=55),  # Rangpur
        _make_report_doc(user_id=admin_uid, lat=22.50, lng=89.00, urgency=50),  # Khulna
    ]
    await db[COLLECTION].insert_many(isolated)

    # 1 STALE report (older than 24h) in the same Sylhet cell.
    stale = _make_report_doc(
        user_id=admin_uid, lat=24.85, lng=91.40,
        severity="critical", urgency=99,
        created_at=_utcnow() - timedelta(hours=48),
    )
    await db[COLLECTION].insert_one(stale)

    # 2 reports owned by the citizen (so the citizen-bbox branch has data).
    citizen_docs = [
        _make_report_doc(user_id=citizen_uid, lat=24.85, lng=91.40, severity="medium", urgency=50),
        _make_report_doc(user_id=citizen_uid, lat=22.30, lng=91.80, severity="low", urgency=20),
    ]
    await db[COLLECTION].insert_many(citizen_docs)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # --- Register citizen (admin is already seeded).
        r = await client.post(
            "/auth/register",
            json={
                "full_name": "Citizen Geo",
                "email": "citizengeo@example.com",
                "password": "goodpass1",
            },
        )
        assert r.status_code == 201, r.text
        citizen_token = r.json()["access_token"]
        actual_citizen_uid = r.json()["user"]["id"]
        # Note: the registered uid is NOT the one we seeded citizen_docs under.
        # We need to fix the seeded docs to use the registered uid, otherwise
        # the citizen-bbox branch returns 0.
        await db[COLLECTION].update_many(
            {"user_id": citizen_uid},
            {"$set": {"user_id": ObjectId(actual_citizen_uid)}},
        )

        # --- Log in as admin (the seeded one).
        r = await client.post(
            "/auth/login",
            json={"identifier": "admingeo@example.com", "password": "goodpass1"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["user"]["role"] == "admin", r.text
        admin_token = r.json()["access_token"]

        admin_h = {"Authorization": f"Bearer {admin_token}"}
        citizen_h = {"Authorization": f"Bearer {citizen_token}"}

        # ===== Step 1 — bbox filter =====
        # Bangladesh spans roughly 88–92.5 E, 20.5–26.5 N.
        # A bbox centered on Sylhet (~24.85, 91.40) of size 0.2° on each side.
        r = await client.get(
            "/api/reports",
            params={"bbox": "91.30,24.75,91.50,24.95"},
            headers=admin_h,
        )
        print("BBOX_SYLHET", r.status_code, "count=", r.json().get("count"))
        assert r.status_code == 200, r.text
        body = r.json()
        # 12 Sylhet reports + 1 stale (still in 91.30,24.75,91.50,24.95 box)
        # + 1 citizen doc also in Sylhet. = 14
        assert body["count"] == 14, f"expected 14 in-box reports, got {body['count']}: {body}"
        for item in body["items"]:
            c = item["location"]["coords"]
            assert 91.30 <= c["lng"] <= 91.50
            assert 24.75 <= c["lat"] <= 24.95

        # Bbox far away (over the Bay of Bengal) → zero results.
        r = await client.get(
            "/api/reports",
            params={"bbox": "95.0,15.0,96.0,16.0"},
            headers=admin_h,
        )
        print("BBOX_FAR", r.status_code, "count=", r.json().get("count"))
        assert r.status_code == 200
        assert r.json()["count"] == 0

        # Malformed bbox → 400.
        r = await client.get(
            "/api/reports",
            params={"bbox": "abc,def,ghi,jkl"},
            headers=admin_h,
        )
        print("BBOX_BAD_FMT", r.status_code)
        assert r.status_code == 400

        # Degenerate bbox (west >= east) → 400.
        r = await client.get(
            "/api/reports",
            params={"bbox": "91.50,24.75,91.30,24.95"},
            headers=admin_h,
        )
        print("BBOX_DEGEN", r.status_code)
        assert r.status_code == 400

        # Bbox outside valid lat range → 400.
        r = await client.get(
            "/api/reports",
            params={"bbox": "90.0,-95.0,91.0,95.0"},
            headers=admin_h,
        )
        print("BBOX_OOR", r.status_code)
        assert r.status_code == 400

        # Backward compat: no bbox returns ALL (12 + 5 + 1 stale + 2 citizen = 20).
        r = await client.get("/api/reports", headers=admin_h)
        print("BBOX_NONE", r.status_code, "count=", r.json().get("count"))
        assert r.status_code == 200
        assert r.json()["count"] == 20, f"expected 20 total, got {r.json().get('count')}"

        # Citizen bbox — only their own reports inside the rectangle.
        r = await client.get(
            "/api/reports",
            params={"bbox": "91.30,24.75,91.50,24.95"},
            headers=citizen_h,
        )
        print("BBOX_CITIZEN", r.status_code, "count=", r.json().get("count"))
        assert r.status_code == 200
        # Citizen owns 1 report in this rectangle (the medium-severity one).
        assert r.json()["count"] == 1

        # ===== Step 2 — hotspots =====
        # Citizen → 403.
        r = await client.get("/api/geo/hotspots", headers=citizen_h)
        print("HOTSPOTS_CITIZEN", r.status_code)
        assert r.status_code == 403

        # Admin → 200 with 1 hotspot (the Sylhet cluster, default 24h window
        # excludes the 48h-old stale one, so 12 + 1 citizen = 13 reports
        # in the cell).
        r = await client.get("/api/geo/hotspots", headers=admin_h)
        print("HOTSPOTS_ADMIN", r.status_code)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 1, f"expected 1 hotspot, got {body['count']}: {body}"
        hot = body["hotspots"][0]
        assert hot["count"] == 13, f"expected 13 in cell, got {hot['count']}"
        assert 91.30 < hot["cell"]["lng"] < 91.50
        assert 24.75 < hot["cell"]["lat"] < 24.95
        assert hot["avg_severity"] == "critical", f"expected critical (worst), got {hot['avg_severity']}"
        assert hot["top_type"] == "flood"
        assert hot["max_urgency"] >= 90
        assert hot["severity_score"] == 4 * 13  # critical=4, count=13

        # Window=72h should still be 13 because the stale one is in Sylhet
        # cell but the in-window count is 13 (12 admin + 1 citizen), not
        # including the stale. Wait — the stale IS 48h old, so 72h includes
        # it. Let me recheck: 12 admin sylhet + 1 stale + 1 citizen = 14.
        r = await client.get(
            "/api/geo/hotspots",
            params={"window": 72},
            headers=admin_h,
        )
        body = r.json()
        print("HOTSPOTS_72H", r.status_code, "count_in_cell=", body["hotspots"][0]["count"] if body["hotspots"] else 0)
        assert body["hotspots"][0]["count"] == 14
        assert body["hotspots"][0]["severity_score"] == 4 * 14

        # min_count=50 (route allows up to 50) → 0 hotspots (no cell has 50).
        r = await client.get(
            "/api/geo/hotspots",
            params={"min_count": 50},
            headers=admin_h,
        )
        body = r.json()
        print("HOTSPOTS_HIGH_BAR", r.status_code, "count=", body["count"])
        assert r.status_code == 200, r.text
        assert body["count"] == 0

        # Out-of-range min_count → 422 (route guard).
        r = await client.get(
            "/api/geo/hotspots",
            params={"min_count": 100},
            headers=admin_h,
        )
        print("HOTSPOTS_OOR", r.status_code)
        assert r.status_code == 422

        # ===== Severity ranking test =====
        # Insert a NEW high-severity cluster in Dhaka (lat 23.7, lng 90.4).
        # Dhaka cell: severity_score = 3 * 3 = 9. Sylhet: 4 * 13 = 52.
        # Sylhet must rank first.
        dhaka_docs = [
            _make_report_doc(user_id=admin_uid, lat=23.70, lng=90.40, severity="high", urgency=70)
            for _ in range(3)
        ]
        await db[COLLECTION].insert_many(dhaka_docs)

        r = await client.get("/api/geo/hotspots", headers=admin_h)
        body = r.json()
        print("HOTSPOTS_RANK", r.status_code, "first=", body["hotspots"][0]["avg_severity"], body["hotspots"][0]["count"])
        # Now we have 2 hotspots.
        assert body["count"] == 2
        # Sylhet (critical, 13) must rank above Dhaka (high, 3).
        assert body["hotspots"][0]["avg_severity"] == "critical"
        assert body["hotspots"][0]["count"] == 13
        assert body["hotspots"][1]["avg_severity"] == "high"
        assert body["hotspots"][1]["count"] == 3

    print("ALL GEO ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())