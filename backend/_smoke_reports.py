"""End-to-end report smoke test using mongomock-motor + httpx ASGI transport.

Covers:
- citizen register + login
- POST /api/report/submit (multipart, with one tiny PNG)
- GET  /api/report/{id}
- GET  /api/reports (list, latest first)
- GET  /api/report/{id}/images/{filename} (download bytes)
- forbidden cross-user GET
- validation: short description rejected
"""
import asyncio
import io

import httpx
from mongomock_motor import AsyncMongoMockClient

import app.core.db as db_mod
import app.models.user as user_model
from app.main import app

# 1x1 PNG, smallest valid PNG payload.
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa3\x9c\xb1\x00"
    b"\x00\x00\x00IEND\xaeB`\x82"
)


async def main() -> None:
    # In-memory Mongo for the whole app.
    mock_client = AsyncMongoMockClient()
    db_mod._client = mock_client
    db_mod._db = mock_client["drrcs_test"]

    try:
        await user_model.ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        print("index note:", exc)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:

        # --- Register two citizens (citizen A submits; citizen B tries to read A's report).
        r = await client.post(
            "/auth/register",
            json={
                "full_name": "Alice Citizen",
                "email": "alice2" + "@" + "example.com",
                "password": "goodpass1",
            },
        )
        assert r.status_code == 201, r.text
        token_a = r.json()["access_token"]
        user_a_id = r.json()["user"]["id"]

        r = await client.post(
            "/auth/register",
            json={
                "full_name": "Bob Citizen",
                "email": "bob2" + "@" + "example.com",
                "password": "goodpass2",
            },
        )
        assert r.status_code == 201, r.text
        token_b = r.json()["access_token"]

        # --- Submit a report with one image, full payload.
        location_obj = {
            "division": "Dhaka",
            "district": "Gazipur",
            "upazila": "Kaliakair",
            "area": "Baipail industrial zone",
            "coords": {"lat": 24.0693, "lng": 90.2221},
        }
        files = [
            ("images", ("flood.png", io.BytesIO(TINY_PNG), "image/png")),
        ]
        data = {
            "description": "Severe flooding in Baipail industrial zone, water level rising.",
            "location": str(location_obj).replace("'", '"'),
            "affected_count": "12",
            "assistance": '["rescue_team", "water", "medical"]',
            "immediate_danger": "true",
            "incident_time": "within_1h",
            "notes": "Roads near the factory gate are submerged.",
            "submitted_at": "2026-07-03T12:34:56.000Z",
        }
        r = await client.post(
            "/api/report/submit",
            data=data,
            files=files,
            headers={"Authorization": f"Bearer {token_a}"},
        )
        print("SUBMIT", r.status_code, {k: r.json().get(k) for k in ("id", "status", "user_id")})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["user_id"] == user_a_id
        assert body["status"] == "pending_ai"
        assert body["ai_output"] is None
        assert body["location"]["division"] == "Dhaka"
        assert body["affected_count"] == 12
        assert body["immediate_danger"] is True
        assert body["incident_time"] == "within_1h"
        assert set(body["assistance"]) == {"rescue_team", "water", "medical"}
        assert len(body["images"]) == 1
        report_id = body["id"]
        image_filename = body["images"][0]["filename"]
        image_url = body["images"][0]["url"]
        assert image_url.startswith(f"/api/report/{report_id}/images/")
        assert image_url.endswith(image_filename)

        # --- Submit a second report so we can verify "latest first".
        r = await client.post(
            "/api/report/submit",
            data={
                "description": "Building collapse reported near the river bank.",
                "location": '{"division": "Chittagong"}',
                "affected_count": "3",
                "immediate_danger": "false",
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )
        print("SUBMIT_2", r.status_code, r.json()["id"])
        assert r.status_code == 201
        second_id = r.json()["id"]

        # --- Fetch one report (owner).
        r = await client.get(
            f"/api/report/{report_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        print("GET_ONE", r.status_code, r.json()["id"])
        assert r.status_code == 200
        assert r.json()["id"] == report_id

        # --- Cross-user GET should be forbidden.
        r = await client.get(
            f"/api/report/{report_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        print("GET_CROSS_USER", r.status_code)
        assert r.status_code == 403

        # --- No-auth GET should be 401.
        r = await client.get(f"/api/report/{report_id}")
        print("GET_NO_AUTH", r.status_code)
        assert r.status_code == 401

        # --- List (citizen sees their own, latest first).
        r = await client.get(
            "/api/reports",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        print("LIST", r.status_code, r.json()["count"])
        assert r.status_code == 200
        assert r.json()["count"] == 2
        assert r.json()["items"][0]["id"] == second_id  # newest first

        # --- Download an image (public).
        r = await client.get(f"/api/report/{report_id}/images/{image_filename}")
        print("GET_IMAGE", r.status_code, len(r.content))
        assert r.status_code == 200
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

        # --- Unknown image should 404.
        r = await client.get(f"/api/report/{report_id}/images/does-not-exist.png")
        print("GET_IMAGE_404", r.status_code)
        assert r.status_code == 404

        # --- Bad description (too short) -> 422.
        r = await client.post(
            "/api/report/submit",
            data={
                "description": "short",
                "location": '{"division": "Dhaka"}',
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )
        print("SUBMIT_BAD_DESC", r.status_code)
        assert r.status_code == 422

        # --- Non-citizen (admin) cannot submit. Seed one inline.
        from app.core.security import hash_password
        from app.models import user as user_model
        admin_doc = {
            "name": "Admin User",
            "email": "admin" + "@" + "example.com",
            "password_hash": hash_password("adminpass1"),
            "role": "admin",
            "created_at": __import__("datetime").datetime.utcnow(),
            "updated_at": __import__("datetime").datetime.utcnow(),
        }
        await db_mod._db[user_model.COLLECTION].insert_one(admin_doc)
        r = await client.post(
            "/auth/login",
            json={"identifier": "admin" + "@" + "example.com", "password": "adminpass1"},
        )
        admin_token = r.json()["access_token"]
        r = await client.post(
            "/api/report/submit",
            data={
                "description": "Admin should not be able to submit.",
                "location": '{"division": "Dhaka"}',
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print("SUBMIT_AS_ADMIN", r.status_code)
        assert r.status_code == 403

    print("\nALL REPORT ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())